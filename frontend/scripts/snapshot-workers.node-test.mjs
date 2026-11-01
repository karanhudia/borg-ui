import assert from 'node:assert/strict'
import { test } from 'node:test'

import { runSnapshotWorkers, resolveSnapshotWorkers } from './snapshot-workers.mjs'

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('captures every job exactly once with bounded simultaneous workers', async () => {
  const gate = deferred()
  const started = []
  const completed = []
  let active = 0
  let peak = 0
  const work = runSnapshotWorkers(
    ['a-desktop', 'b-desktop', 'a-mobile', 'b-mobile', 'c-mobile'],
    async (job) => {
      started.push(job)
      active += 1
      peak = Math.max(peak, active)
      await gate.promise
      completed.push(job)
      active -= 1
    },
    { workers: 2 }
  )
  await Promise.resolve()
  assert.deepEqual(started, ['a-desktop', 'b-desktop'])
  gate.resolve()
  await work
  assert.equal(peak, 2)
  assert.deepEqual(completed.sort(), ['a-desktop', 'a-mobile', 'b-desktop', 'b-mobile', 'c-mobile'])
})

test('serial mode finishes each job before starting the next', async () => {
  const events = []
  await runSnapshotWorkers(
    [1, 2],
    async (job) => {
      events.push(`start ${job}`)
      await Promise.resolve()
      events.push(`end ${job}`)
    },
    { workers: 1 }
  )
  assert.deepEqual(events, ['start 1', 'end 1', 'start 2', 'end 2'])
})

test('worker failure stops new jobs and settles active workers before owner teardown', async () => {
  const failure = new Error('capture failed')
  const gate = deferred()
  const events = []
  const capture = runSnapshotWorkers(
    [1, 2, 3],
    async (job) => {
      events.push(`start ${job}`)
      try {
        if (job === 1) throw failure
        await gate.promise
        throw new Error('second worker also failed')
      } finally {
        events.push(`closed ${job}`)
      }
    },
    { workers: 2 }
  ).finally(() => events.push('browser closed'))
  const rejected = assert.rejects(capture, (error) => error === failure)
  await new Promise(setImmediate)
  assert.deepEqual(events, ['start 1', 'closed 1', 'start 2'])
  gate.resolve()
  await rejected
  assert.deepEqual(events, ['start 1', 'closed 1', 'start 2', 'closed 2', 'browser closed'])
})

test('cancellation stops scheduling but drains active captures before rejecting', async () => {
  const controller = new AbortController()
  const gate = deferred()
  const started = []
  const reason = new Error('cancelled')
  let settled = false
  const work = runSnapshotWorkers(
    [1, 2, 3],
    async (job) => {
      started.push(job)
      await gate.promise
    },
    { workers: 2, signal: controller.signal }
  ).finally(() => {
    settled = true
  })
  const rejected = assert.rejects(work, (error) => error === reason)
  controller.abort(reason)
  await new Promise(setImmediate)
  assert.equal(settled, false)
  assert.deepEqual(started, [1, 2])
  gate.resolve()
  await rejected
  assert.deepEqual(started, [1, 2])
})

test('already cancelled pools never capture a job', async () => {
  const signal = AbortSignal.abort(new Error('cancelled'))
  let captured = false
  await assert.rejects(
    runSnapshotWorkers(
      [1],
      async () => {
        captured = true
      },
      { signal }
    )
  )
  assert.equal(captured, false)
})

test('empty input completes without captures', async () => {
  let captured = false
  await runSnapshotWorkers([], async () => {
    captured = true
  })
  assert.equal(captured, false)
})

test('worker configuration defaults conservatively and rejects invalid limits before work', async () => {
  assert.equal(resolveSnapshotWorkers({}), 2)
  assert.equal(resolveSnapshotWorkers({ STORYBOOK_SNAPSHOT_WORKERS: '1' }), 1)
  assert.equal(resolveSnapshotWorkers({ STORYBOOK_SNAPSHOT_WORKERS: '4' }), 4)
  for (const value of ['', '0', '-1', '1.5', 'NaN', 'Infinity', '2x', '17']) {
    assert.throws(() => resolveSnapshotWorkers({ STORYBOOK_SNAPSHOT_WORKERS: value }))
  }
  for (const workers of [0, -1, 1.5, Infinity, NaN, 17, '2']) {
    let captured = false
    await assert.rejects(
      runSnapshotWorkers(
        [1],
        async () => {
          captured = true
        },
        { workers }
      )
    )
    assert.equal(captured, false)
  }
})
