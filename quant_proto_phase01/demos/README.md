# QSwitch Demos

Four ways to experience the QSwitch higher-order quantum programming demo:

## 1. Static Output (`qswitch_demo_output.md`)

For those who just want to see the results without running code.

**View:** Open `qswitch_demo_output.md` in any markdown viewer.

## 2. Runnable Script (`qswitch_demo.py`)

For those with the infrastructure installed (Python + pytket).

**Requirements:**
```bash
pip install pytket
```

**Run:**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo.py
```

## 3. HTML Animation (`qswitch_demo.html`)

Interactive browser-based demo with play/pause controls.

**View:** Open `qswitch_demo.html` in any web browser.

- Click **▶ Play Demo** to watch the animated output
- Click **⏩ Show All** to see everything at once
- Click **↺ Reset** to start over

No installation required - works offline in any browser.

## 4. Video Recording Script (`qswitch_demo_video.py`)

For creating a video demo or watching with visual timing.

**Option A: Direct run (slow, visual)**
```bash
cd quant_proto_phase01
PYTHONPATH=src python demos/qswitch_demo_video.py
```

**Option B: Record with asciinema**
```bash
# Install asciinema: pip install asciinema
cd quant_proto_phase01
asciinema rec -c "PYTHONPATH=src python demos/qswitch_demo_video.py" qswitch_demo.cast

# Play back:
asciinema play qswitch_demo.cast

# Upload to share:
asciinema upload qswitch_demo.cast
```

**Option C: Screen recording**

Use any screen recording tool (OBS, QuickTime, etc.) while running the video script.

---

## What the Demo Shows

1. **QSwitch Definition** - Higher-order quantum combinator
2. **QSwitch(H, S)** - Instantiation with Hadamard and S gates
3. **First-Order Circuit** - 5 gates on 2 qubits
4. **GOI Conjugation Form** - 10 gates on 4 qubits (doubled up)
5. **GOI Verification** - twist;twist=id, H;S composition
