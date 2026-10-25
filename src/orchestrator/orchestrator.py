"""Dependency-driven research execution with bounded work and partial results."""
from __future__ import annotations
import asyncio
import copy
import time
import uuid
from .schemas import OrchestratorState as State, SubTask, AgentResult, AgentStatus, ResearchReport, RunConfig, TaskType
from ..planner.budget_tracker import BudgetTracker
from ..utils.async_call import call_sync, request_deadline
from ..utils.sources import result_sources
from ..utils.tracing import trace_chain


class Orchestrator:
    def __init__(self, planner, agent_pool, budget_tracker=None, compressor=None,
                 adversarial_loop=None, memory_store=None, summarizer_policy=None):
        self.planner, self.agent_pool = planner, agent_pool
        self.budget_tracker = budget_tracker or BudgetTracker()
        self.compressor, self.adversarial_loop = compressor, adversarial_loop
        self.memory_store, self.summarizer_policy = memory_store, summarizer_policy
        self._results, self._memory_store, self._task_map = [], {}, {}
        self._dag, self._current_state = None, State.IDLE
        self._config, self._query = RunConfig(), ''
        self._run_id, self._running = '', False
        self._replan_count = self._adversarial_count = 0
        self._deadline = self._work_deadline = float('inf')
        self._timed_out, self._pending, self.events = False, set(), []

    def _state(self, state):
        self._current_state = state
        self.events.append({'state': state.value, 'elapsed': round(time.monotonic()-self._start_time, 4)})
        print(f'[Orchestrator] State transition: {state.value}')

    async def run(self, query, config=None):
        # LangSmith reserves the keyword 'config' for a mapping, not RunConfig.
        return await self._run(query, run_config=config)

    @trace_chain(name='orchestrator.run', tags=['m1', 'orchestrator'])
    async def _run(self, query, run_config=None):
        if self._running:
            raise RuntimeError('Use a separate Orchestrator for concurrent runs')
        self._config = run_config or RunConfig()
        if self._config.max_concurrent < 1 or self._config.global_timeout_seconds <= 0:
            raise ValueError('Concurrency and timeout must be positive')
        self._running = True
        self._query, self._run_id = query, uuid.uuid4().hex
        self._results, self._memory_store, self._task_map = [], {}, {}
        self._pending, self.events = set(), []
        self._replan_count = self._adversarial_count = 0
        self._timed_out = False
        self._start_time = time.monotonic()
        self._deadline = self._start_time + self._config.global_timeout_seconds
        reserve = min(max(0, self._config.synthesis_reserve_seconds), self._config.global_timeout_seconds * .2)
        self._work_deadline = self._deadline - reserve
        # Isolate last-plan mutations made by a late synchronous planner.
        self._planner = copy.copy(self.planner)
        self._planner.max_tasks = self._config.max_sub_questions
        deadline_token = request_deadline.set(self._deadline)
        try:
            self._state(State.PLANNING)
            try:
                memory = await self._bounded(call_sync(self._build_memory_context), work=True)
                self._dag = await self._bounded(call_sync(self._planner.generate_plan, query, memory), work=True)
                self._load_plan()
                while True:
                    self._state(State.DISPATCHING)
                    await self._do_dispatching()
                    self._state(State.COLLECTING)
                    if self._timed_out or not self._should_replan(self._results):
                        break
                    if self._replan_count >= self._config.max_replan_rounds:
                        break
                    self._state(State.REPLANNING)
                    await self._do_replanning()
            except asyncio.TimeoutError:
                self._timed_out = True
            except Exception as exc:
                self.events.append({'error': type(exc).__name__, 'message': str(exc)})
            self._state(State.SYNTHESIZING)
            await self._do_synthesizing()
            report = self._memory_store['final_report']
            if report.status == 'completed' and self._config.enable_adversarial and self.adversarial_loop:
                self._state(State.ADVERSARIAL)
                try:
                    report, history = await self._bounded(self.adversarial_loop.run(report))
                    report.review_history = history
                    self._adversarial_count = len(history)
                    report.review_status = ('budget_exhausted' if any(
                        h.get('stop_reason') in ('model_budget_exhausted', 'insufficient_fix_budget')
                        for h in history) else 'completed')
                except asyncio.TimeoutError:
                    report.review_status = 'timeout'
                    self.events.append({'review': 'timeout; original report retained'})
                except Exception as exc:
                    report.review_status = 'failed'
                    self.events.append({'review_error': str(exc)})
            elif self._config.enable_adversarial and self.adversarial_loop:
                report.review_status = 'skipped_incomplete'
            report.run_id = self._run_id
            report.num_replan, report.adversarial_rounds = self._replan_count, self._adversarial_count
            self._memory_store['final_report'] = report
            self._state(State.FAILED if report.status == 'failed' else State.DONE)
            return report
        except asyncio.CancelledError:
            self._state(State.FAILED)
            self.events.append({'cancelled': True})
            raise
        finally:
            request_deadline.reset(deadline_token)
            self._running = False

    async def _bounded(self, awaitable, *, work=False):
        remaining = (self._work_deadline if work else self._deadline) - time.monotonic()
        return await asyncio.wait_for(awaitable, max(0, remaining))

    def _load_plan(self):
        new_map = self._planner.get_task_map_from_dag(self._dag, self._planner._last_raw_json)
        for result in self._results:
            old = self._task_map.get(result.task_id)
            new = new_map.get(result.task_id)
            if result.status == AgentStatus.SUCCESS and old and new and old != new:
                raise ValueError('A successful task ID cannot be reused for a changed task')
        self._task_map = new_map
        if len(self._task_map) > self._config.max_sub_questions:
            raise ValueError('Plan exceeds max_sub_questions')
        if set(self._task_map) != set(self._dag):
            raise ValueError('Every DAG node needs a complete SubTask')
        retired = [r for r in self._results if r.status != AgentStatus.SUCCESS and r.task_id not in self._task_map]
        for result in retired:
            self.events.append({'superseded_task': result.task_id, 'status': result.status.value})
        self._results = [r for r in self._results if r.status == AgentStatus.SUCCESS or r.task_id in self._task_map]
        self._pending = set(self._task_map) - {r.task_id for r in self._results if r.status == AgentStatus.SUCCESS}

    def _publish(self, result):
        self.events.append({'task_id': result.task_id, 'task_status': result.status.value,
                            'failure_reason': str(result.output)[:500] if result.status != AgentStatus.SUCCESS else None})
        self._memory_store[f'result:{result.task_id}'] = result
        self._results = [r for r in self._results if r.task_id != result.task_id] + [result]
        self._pending.discard(result.task_id)

    async def _do_dispatching(self):
        semaphore = asyncio.Semaphore(self._config.max_concurrent)
        for group in self._dag.get_parallel_groups():
            async def execute(task_id):
                existing = self._memory_store.get(f'result:{task_id}')
                if existing and existing.status == AgentStatus.SUCCESS:
                    return existing
                task = self._task_map[task_id]
                async with semaphore:
                    missing = [d for d in task.dependencies if not self._memory_store.get(f'result:{d}')
                               or self._memory_store[f'result:{d}'].status != AgentStatus.SUCCESS]
                    if missing:
                        return AgentResult(task_id, AgentStatus.FAILED, output=f'Blocked by failed dependencies: {missing}')
                    context = await self._bounded(call_sync(self._build_task_context, task), work=True)
                    agent = await self.agent_pool.get_agent(task.task_type)
                    try:
                        for attempt in range(self._config.max_subagent_retries + 1):
                            try:
                                remaining = self._work_deadline-time.monotonic()
                                if remaining <= 0:
                                    raise asyncio.TimeoutError
                                result = await asyncio.wait_for(agent.run(task, context), min(task.timeout_seconds, remaining))
                                break
                            except (ConnectionError, OSError):
                                if attempt >= self._config.max_subagent_retries:
                                    raise
                        return result
                    except asyncio.TimeoutError:
                        agent._discard = True
                        if time.monotonic() >= self._work_deadline:
                            self._timed_out = True
                        return AgentResult(task_id, AgentStatus.TIMEOUT, output='Task deadline exceeded')
                    except Exception as exc:
                        return AgentResult(task_id, AgentStatus.FAILED, output=f'{type(exc).__name__}: {exc}')
                    except asyncio.CancelledError:
                        agent._discard = True
                        raise
                    finally:
                        await self.agent_pool.release_agent(agent)
            jobs = {asyncio.create_task(execute(tid)): tid for tid in group}
            try:
                done, pending = await asyncio.wait(jobs, timeout=max(0, self._work_deadline-time.monotonic()))
                for job in done:
                    try:
                        result = job.result()
                    except Exception as exc:
                        result = AgentResult(jobs[job], AgentStatus.FAILED, output=str(exc))
                    self._publish(result)
                if pending:
                    self._timed_out = True
                    for job in pending:
                        job.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for job in pending:
                        self._publish(AgentResult(jobs[job], AgentStatus.TIMEOUT, output='Global work deadline exceeded'))
            finally:
                for job in jobs:
                    if not job.done():
                        job.cancel()
                await asyncio.gather(*jobs, return_exceptions=True)
            if self.memory_store is not None and not self._timed_out:
                for tid in group:
                    result = self._memory_store.get(f'result:{tid}')
                    if result and result.status == AgentStatus.SUCCESS:
                        try:
                            await self._bounded(call_sync(self._sync_result_to_memory_store, result), work=True)
                        except asyncio.TimeoutError:
                            self._timed_out = True
                            break
            if self._timed_out:
                break
        return State.COLLECTING

    async def _do_replanning(self):
        self._replan_count += 1
        failed = [self._task_map[r.task_id] for r in self._results
                  if r.status != AgentStatus.SUCCESS and r.task_id in self._task_map]
        self._dag = await self._bounded(call_sync(self._planner.replan, query=self._query,
            failed_tasks=failed, existing_results=list(self._results), reason='Failed dependencies, tools or timeouts'), work=True)
        self._load_plan()
        return State.DISPATCHING

    def _fallback_report(self, reason):
        valid = [r for r in self._results if r.status == AgentStatus.SUCCESS and r.output]
        failed = sorted(self._pending | {r.task_id for r in self._results if r.status != AgentStatus.SUCCESS})
        return ResearchReport(query=self._query,
            content='\n\n'.join([reason]+[f'## {r.task_id}\n{r.output}' for r in valid]),
            sources=result_sources(valid), status='partial' if result_sources(valid) else 'failed', incomplete_tasks=failed,
            num_searches=sum(sum(t.get('role')=='tool' for t in r.trajectory) for r in self._results))

    async def _do_synthesizing(self):
        from ..agents.summarizer import SummarizerAgent
        valid = [r for r in self._results if r.status == AgentStatus.SUCCESS and r.output]
        if not valid or self._deadline <= time.monotonic():
            report = self._fallback_report('Evidence insufficient or global deadline reached; no complete research report.')
        else:
            borrowed = None
            try:
                policy = self.summarizer_policy
                if policy is None:
                    borrowed = await self.agent_pool.get_agent(TaskType.ANALYZE)
                    policy = borrowed.policy
                agent = SummarizerAgent('summarizer', policy)
                result = await self._bounded(agent.run(SubTask('synthesize_final', TaskType.ANALYZE, 'Synthesize evidence'),
                    {'query': self._query, 'results': valid, 'compressor': self.compressor}))
                if result.status != AgentStatus.SUCCESS:
                    raise RuntimeError(str(result.output))
                report = result.output
                report.incomplete_tasks = sorted(self._pending | {r.task_id for r in self._results if r.status != AgentStatus.SUCCESS})
                if self._timed_out or report.incomplete_tasks:
                    report.status = 'partial'
                    report.content += '\n\nIncomplete tasks: ' + ', '.join(report.incomplete_tasks)
            except Exception as exc:
                report = self._fallback_report(f'Synthesis incomplete ({type(exc).__name__}); available findings follow.')
            finally:
                if borrowed:
                    await self.agent_pool.release_agent(borrowed)
        self._memory_store['final_report'] = report
        return State.DONE

    def _should_replan(self, results):
        return bool(results) and sum(r.status != AgentStatus.SUCCESS for r in results)/len(results) > .5

    def _is_global_timeout(self):
        return time.monotonic() >= self._deadline

    def _build_memory_context(self):
        if self.memory_store is not None:
            return self.memory_store.get_context_for_query(self._query, max_tokens=2000)
        return ''

    def _build_task_context(self, task):
        context = {'query': self._query, 'compressor': self.compressor}
        for dep in task.dependencies:
            result = self._memory_store.get(f'result:{dep}')
            if result and result.status == AgentStatus.SUCCESS:
                context[f'dep:{dep}'] = result
        if self.memory_store is not None:
            context['research_memory'] = self.memory_store.get_context_for_query(task.description, max_tokens=2000)
        return context

    def _sync_result_to_memory_store(self, result):
        from ..memory.long_term import MemoryEntry
        entry = MemoryEntry(entry_id=f'{self.memory_store.session_id}:{self._run_id}:{result.task_id}',
            claim=str(result.output)[:2000], source=f'task:{result.task_id}', confidence=result.confidence,
            agent_id=result.task_id, timestamp=time.time(), evidence_type='secondary', embedding=[], topic=self._query[:50],
            metadata={'run_id': self._run_id, 'task_id': result.task_id, 'sources': result_sources([result])})
        self.memory_store.put(entry)
