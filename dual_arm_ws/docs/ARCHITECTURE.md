# Architecture

The authoritative specification is REQUIREMENTS.md. Build simulation first on Ubuntu 24.04 / ROS 2 Jazzy / Gazebo Harmonic, then validate physical deployment independently.

Description owns the two four-joint chains and TCP frames. Gazebo owns contact physics, cameras and simulated suction. MoveIt owns collision-aware planning. ros2_control owns execution; controllers have disjoint joints. One CM530SystemInterface instance owns the physical serial port.

Upstream vision interfaces remain intact. The adapter owns calibration provenance, image freshness, frame checks and conversion. Services without timestamps require correlated timestamped perception evidence; a response alone cannot authorize motion. Home-specific homographies are valid only at their calibrated pose. Calibration thresholds must be derived from measured clearance, cup geometry and mechanical uncertainty, not defaults.

Coordinator owns the A/B/C state machine. B ownership is released only after confirmed withdrawal, never merely on a timeout. Slots are committed only after vision verifies placement. Gripper feedback and MoveIt attached collision objects must agree.

Implementation map: `dual_arm_coordinator/workflow` holds the ROS-free A/B/C state machine, `journal.py` the persistent record, and `coordinator_node.py` the services and watchdog. `gateways/` holds the ROS adapters: `motion` (downward IK, joint goals, sampled contact paths, PlanningScene, arrival checks), `gripper` (Gazebo, manual token, ESP32), `truth` (simulation observations) and `vision` (calibration and image gates, TF conversion). `safety_supervisor` deactivates the arm controllers when the emergency-stop heartbeat or the coordinator is lost; it is a software interlock and does not replace a physical stop.

Zone and slot observations still come from Gazebo ground truth, and only the arm 1 pick target comes from vision, because the fixed simulated cameras are occluded at HOME. The coordinator refuses hardware mode until this and the hardware TF are resolved.

The operator interface (`dual_arm_hmi`, UI_PLAN.md) is a client of these services. A read-only monitor node subscribes and queries; a separate command node calls `/dual_arm/{start,cancel,go_home,recover}` and `/safety/{trigger_stop,reset}`, and the `--monitor` window never creates it. It starts and stops the system as its own process group, runs hardware on a ROS domain separate from simulation, and never opens the serial port or publishes `/safety/estop`. Its stop button is a software stop through `safety_supervisor`, not a replacement for the physical emergency stop.

Simulation and hardware evidence are stored separately. No default matrix authorizes hardware.
