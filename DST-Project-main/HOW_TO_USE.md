# DST Emulator — How to Use

Live app: [dst-emulator.vercel.app](https://dst-emulator.vercel.app)

## Quick start

1. Open **To-Do & Clock** → add at least one task (reminders need a task).
2. Set **timezone** (e.g. Eastern) and a **Daily Reminder** time.
3. Open **DST Emulator** → set the clock (preset or manual) → advance with **+1 Sec / +1 Min**.
4. When the clock crosses the reminder time → alert fires → tasks are struck through → check **Trigger Log**.

The clock does **not** run by itself. You must press the step buttons.

---

## DST test timings (+1 Sec)

Use these in **Manually Set Date & Time**, then press **Set**, then **+1 Sec**.

| Scenario | Input time | What to do |
|---|---|---|
| **Spring Forward** | `2026-03-08 01:59:55 EST` | Set reminder to `02:30`. Press **+1 Sec** until the clock jumps past 2:00 → 3:00 AM EDT (2:00–2:59 is skipped). Reminder at 2:30 fires with a spring-forward adjustment. |
| **Fall Back** | `2026-11-01 01:29:55 EDT` | Set reminder to `01:30`. Press **+1 Sec** to cross 1:30 on the first (EDT) occurrence of the repeated hour. |

### Copy-paste values

```
Spring forward:  2026-03-08 01:59:55 EST
Fall back:       2026-11-01 01:29:55 EDT
```

Or use the **Spring Forward** / **Fall Back** preset cards (same idea; then step with +1 Sec / +1 Min).

---

## Tips

- Reminder must be **ahead of** the current emulator clock for the next tick to cross it.
- Changing reminder time resets that day’s trigger so you can retest.
- **Clear Logs** wipes the trigger history.
- Frontend and API are separate Vercel apps; session state is kept in the browser for each visit.
