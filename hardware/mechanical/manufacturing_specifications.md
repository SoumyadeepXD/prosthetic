# VAPA Mechanical Manufacturing & Assembly Specifications

## 1. 3D Printing Production Parameters

All structural components must adhere to the following slicer settings to ensure mechanical strength and layer adhesion under cyclic 200 N tendon tension:

| Component Category | Recommended Slicer Setting | Quality Standard |
| :--- | :--- | :--- |
| **Material** | Carbon Fiber PETG (PETG-CF) or PA12-CF | Dried for 6 hours at 70°C prior to printing. |
| **Nozzle Diameter** | 0.40 mm hardened steel or ruby | Brass nozzles wear prematurely from CF fibers. |
| **Layer Height** | 0.16 mm (Structural), 0.12 mm (Joints) | Fine layer resolution prevents stepping on tendon radius guides. |
| **Perimeter Walls** | 5 minimum (2.0 mm total wall thickness) | Critical for holding heat-set inserts without wall blow-out. |
| **Top / Bottom Layers** | 6 solid layers minimum | Prevents deflection under screw head torque. |
| **Infill Density** | 50% Gyroid or Cubic | Gyroid infill provides isotropic shear resistance against torsional loads. |
| **Print Speed** | 45 mm/s outer wall, 60 mm/s inner wall | Slower speeds ensure maximum inter-layer bonding strength. |

---

## 2. Heat-Set Insert Installation Standard

All fasteners thread into brass heat-set inserts (Ruthex style with diagonal knurling). Never thread steel screws directly into thermoplastic:
1. **Tooling**: Temperature-controlled soldering station equipped with a flat-bottomed insert installation tip.
2. **Temperature**: Set iron to **235°C–245°C** for PETG-CF; **260°C–270°C** for PA12-CF.
3. **Procedure**:
   - Align insert squarely over pilot hole.
   - Apply gentle, steady downward axial pressure. Allow heat to soften surrounding plastic without forcing.
   - Stop when insert face is **0.1 mm below** the plastic surface.
   - Immediately remove iron and hold square with a flat brass plate for 5 seconds to cool.
   - Clean any molten plastic flash from internal threads using an M2/M2.5/M3 bottoming tap.

---

## 3. Joint Pin & Bearing Press-Fit Standard

1. **Finger Pivots**:
   - Press 2x MF63ZZ flanged bearings into the outer pocket of each phalanx knuckle using a parallel-jaw arbor press or miniature vice.
   - Slide precision ground 3.0 mm h6 dowel pin through inner knuckle.
   - Axial float must be between **0.10 mm and 0.25 mm**. If joint binds, lightly dress inner knuckle face with 600-grit sandpaper.
2. **Forearm Slewing Bearing**:
   - 6808-2RS bearing press-fit into forearm socket adapter.
   - Retained axially with an aluminum internal snap ring (DIN 472).
