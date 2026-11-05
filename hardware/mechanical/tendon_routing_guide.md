# VAPA Tendon Routing, Rigging & Pre-Tensioning Guide

## 1. Material & Tooling Preparation
- **Tendon Line**: 0.50 mm 8-strand braided Dyneema (UHMWPE) line, minimum breaking strength 100 lb (445 N).
- **Liner Sheath**: Smooth-bore Virgin PTFE tubing (1.0 mm ID × 2.0 mm OD).
- **Crimping Sleeves**: Dual-barrel copper or aluminum fishing crimp sleeves (0.8 mm bore).
- **Adhesive**: Cyanoacrylate (medium viscosity) for locking knots and tendon terminations.

---

## 2. Step-by-Step Stringing Procedure

### Step 1: Liner Installation
1. Cut PTFE liner tubing to length for each finger path:
   - Palm-to-MCP: 38 mm
   - MCP-to-PIP: 22 mm
   - PIP-to-DIP: 18 mm
2. Flare both tube ends using a heated 60° punch tool to prevent tendon chafing against sharp tubing edges.
3. Seat liners into their molded guide grooves in each phalanx.

### Step 2: Distal Phalanx (Fingertip) Termination
1. Thread Dyneema line through the distal phalanx anchor hole.
2. Form a figure-eight stopper knot followed by two half-hitches.
3. Wet the knot thoroughly with cyanoacrylate adhesive and let cure for 5 minutes.
4. Seat the knotted end firmly into the recessed termination pocket behind the FSR sensor cavity.

### Step 3: Routing Through Knuckle Bearings
1. Thread the line proximally through the DIP, PIP, and MCP knuckle grooves.
2. Verify the line runs smoothly over the curved radius tracks and does not rub against the stainless steel pivot pins.

### Step 4: Capstan Spool Attachment & Pre-Tensioning
1. Mount the 25 mm diameter capstan spool to the MG996R servo horn.
2. With the servo commanded to **0.0 (Home / Fully Open position)**, thread the tendon into the spool entry eyelet.
3. Wrap 1.5 dead turns clockwise around the spool drum groove.
4. Hang a **500 g calibration weight** on the free end of the line to establish initial pre-tension (eliminates mechanical slack).
5. Pass the line through a dual-barrel crimp sleeve, pull snug, and crimp with four-jaw swaging pliers.
6. Trim excess line, leaving a 5 mm tail. Seal tail with cyanoacrylate.

---

## 3. Extension Return Spring Setup
1. Each joint features dual torsional return springs (0.4 mm music wire, 2.5 active coils) mounted concentric to the pivot pin.
2. With the finger fully closed, spring torque must not exceed **0.15 N·m** to avoid wasting motor stall torque.
3. When tendon tension is released by the servo, the return springs must extend the finger to 0° within **< 100 ms**.
