# Prototype direct transfer (no HOME between zones) — 2026-11-17

User decision 2026-11-17: speed up the prototype flow, starting with the HOME detour.

## Why

The 2026-11-17 field video (one object A → B → C, about 153 s from arm 1 starting to arm 2 back
HOME, read from frames at 1 s steps) showed both arms returning HOME in the middle of a transfer:

| Time | What | s |
|---|---|---|
| 0:32–0:40 | arm 1, holding the cap, back to HOME | 8 |
| 0:40–0:54 | arm 1 HOME → above B | 14 |
| 1:44–1:52 | arm 2, holding the cap, back to HOME | 8 |
| 1:52–2:02 | arm 2 HOME → above C | 10 |

That is the `HOME_HOLDING` step of both workflows. Estimated saving 20–25 s per object
(not measured).

## Change (prototype only, `direct_transfer: true`)

- Arm 1 takes zone B inside `PREFLIGHT`, with the `CHECK_ZONES` view (both arms HOME, B empty),
  then goes above A → pick → above B directly. `HOME_HOLDING` and the second `RESERVE_B` are skipped.
- Arm 2 goes above B → pick → above C directly. `HOME_HOLDING` and `VERIFY_B_EMPTY` are skipped;
  the same check (B empty and both arms HOME) runs inside `VERIFY_C`, on the view that also checks
  C, and only then is B released. Arm 2 therefore owns B until it is HOME again.
- The reordered checks sit in existing steps so the interface progress never steps back.
- Without the key (simulation, strict hardware) the flow is unchanged.

## Checks

| Check | Result | File |
|---|---|---|
| Coordinator unit tests (12 new) | PASS 437 | coordinator_tests.txt |
| HMI unit tests | PASS 320 | hmi_tests.txt |
| Prototype config validation | PASS | prototype_config_check.txt |
| Direct moves through MoveIt (path from above A to above B holding a cap, above B to above C) | NOT_RUN | |
| Real arms | NOT_RUN | |

## Transport speed (same day, user decision)

Prototype `transport_scale` 0.3 → 0.6: planned moves now run at up to 0.3 rad/s (URDF limit
0.5 rad/s) instead of 0.15. Contact moves are left as they were: `contact_scale` stays 0.2 and
`acceleration_scale` stays 0.3, because the contact trajectories also use it. Config validation and
coordinator tests rerun: `prototype_config_check_speed.txt` PASS, `coordinator_tests_speed.txt`
PASS 437. Real arms NOT_RUN. The driver faults when a joint target moves more than
`max_step_raw` (20 counts) between two sent commands; the scheduler cycle time on the Orin was not
measured, so watch the log for `exceeds max_step_raw`.

Risk to watch on the real arms: MoveIt now plans A → B and B → C with the cap attached, without the
upright HOME in between; the path may sweep lower over the field than before.
