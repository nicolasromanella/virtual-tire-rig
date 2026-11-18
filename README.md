# Virtual Tire Characterization Rig

Version 1.4 · by [Nicolas Romanella](https://nicolasromanella.com)

A virtual test rig for one wheel with its tire, written from scratch in Python.
The belt imposes the road speed, the wheel can be steered through any angle,
and drive and brake torques act on the rim, while forces, slips and tire
characteristics update live.

**Try it in your browser:** [nicolasromanella.com/apps/virtual-tire-rig](https://nicolasromanella.com/apps/virtual-tire-rig/)  
**Model and verification:** [Virtual_Tire_Characterization_Rig_v1.4.pdf](Virtual_Tire_Characterization_Rig_v1.4.pdf)

## Run locally

```
python -m pip install -r requirements.txt
python main.py
```

Python 3.12 recommended.

Tire coefficients: PAC2002 lateral set of the Project Chrono sedan tire (`Sedan_Pac02Tire.tir`, BSD-3-Clause), as noted in `rig/tyre.py`.

## Controls

- **Tab** switch Drive / Test, **R** reset, **1 / 2 / 3** Plots, Transient, Forces, **Esc** quit
- **Drive**: arrows steer, throttle and brake (a game controller works too)
- **Test**: left / right change the steer angle, up / down the drive and brake torques; or drag the sliders
- Drag a 3D view to rotate it, right click resets it

## License

All rights reserved. You may read the code and run it to evaluate it.
Any other use needs written permission. See [LICENSE](LICENSE).
