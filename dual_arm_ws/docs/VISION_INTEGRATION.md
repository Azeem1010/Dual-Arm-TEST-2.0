# Vision integration

The original packages are copied intact to src, pinned in docs/sources.lock.json.
`vision_sim.launch.py` launches the original env_vision_node, arm1_vision_node and arm2_vision_node against Gazebo image topics. It does not start USB devices.

Original service definitions and names remain unchanged. GetPickTarget response: success, message, rank, x/y/z. GetGridState response: occupied[8], place_x/y/z[8], all_full, success, message. VerifyPlace response: placed, order_ok, wrong_slots, success, message. These responses have no image acquisition timestamp.

Upstream frames use arm1_base / arm2_base; integration model uses arm1_base_link / arm2_base_link. A motion adapter must explicitly map and verify those frames with TF rather than merely relabel coordinates. `gateways/vision.py` now does this for the pick target, converting `arm1_base` to `world` through TF; the hardware TF does not exist yet. `sim.launch.py` publishes the fixed `armN_base_link` to `armN_base` transforms for simulation only. Axis definitions are in [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md).

CalibrationStatus publishes diagnostic messages and fails closed with missing records. With `observation_source:=vision_pick` the coordinator refuses a pick unless the arm 1 status is a recent PASS and a new image arrived after the arm settled. Zone and slot observations still use Gazebo ground truth because the fixed simulated cameras are occluded by the arms at HOME (conflict C31, decision D7). No automatic physical motion is exposed: the coordinator refuses hardware mode.
