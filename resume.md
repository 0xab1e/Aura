# Able Eldhose

**Location:** Bangalore
**Phone:** +91 9946333898
**Email:** able.eldhose@outlook.com
**LinkedIn:** https://www.linkedin.com/in/able-eldhose/

---

## Professional Summary

Embedded professional with 14 years experience in design & development in AI compiler, Embedded Edge AI, TensorFlow Lite runtime, IoT domain, and Embedded Firmware. Experience in mentoring, leading projects, design, development and project execution.

---

## Work History

**Synaptics (continued from ETA Compute)** — Senior Staff Software Engineer (T5)
June 2020 – Present (6 years)

**OYO – Oravel Stays Private Limited** — Project Lead
July 2019 – June 2020 (~1 year)

**Broadcom Limited** — R&D Engineer Software-2
July 2015 – July 2019 (4 years)

**VVDN Technologies** — Engineer – Software
September 2014 – July 2015 (~1 year)

**SFO Technologies** — Firmware Engineer
September 2012 – September 2014 (2 years)

**Ebird Innovation** — Firmware Trainee
June 2012 – September 2012 (4 months)

---

## Skills

- Experience in Edge AI runtime and compiler implementation
- Developed AI compiler for uNPU's based on Vela compiler by ARM
- Patents in progress regarding algorithms for accelerating TensorFlow int8 operators in runtime
- Hands on experience in TensorFlow Lite Micro implementation and architecture
- Expertise in building and maintaining firmware for MCUs from scratch
- Experience in building firmware for power efficient and battery operated devices
- Expertise in RTOS as well as bare metal firmware projects
- Flair in automating tedious and repetitive tasks using Python scripts
- Experienced in building various IoT applications across wireless technologies (WiFi, BLE)
- Controller side FW development for Bluetooth RF chips
- Well experienced in dissecting a project into short-term milestones and long-term goals
- Well experienced in Embedded C and Assembly language
- Knowledge on ARM register set and assembly language programming
- Good skills in optimizing code for speed/size, reducing mathematical operation cycles in C
- Hands on experience in debugging using MSO, digital probes etc

---

## Professional Projects

### SynAI Compiler (Synaptics)
Complete ownership of the new generation of SynAI compiler for multiple generations of chips. Generates layer descriptors specific to the chip being compiled for. Computes and re-orders weights offline to save run-time computations. Supported operators are converted to custom operators with metadata to make the runtime faster.

### SynAI Automated Test Suite (Synaptics)
Developed a test suite with a pool of test models which are compiled, run and verified on HW. Collects cycle count, verifies output with TensorFlow reference and provides deviation statistics. Extended for CI/CD automation.

### uNPU Cycle Count Estimator (Synaptics)
Proposed, designed and developed a test suite which creates models with vast variations of operators with different shapes and parameters, compiles and runs them in uNPU, collects cycle count per layer, trains a tiny ML model with parameters and cycle count. The trained parameters are used in SynAI compiler to estimate cycle count with less than 8% error — a major boost to the marketing team.

### SynAI C Model Simulator (Synaptics)
Significant contributor to a C model simulator used as a validation and quick development platform. First-level environment to test and fix bugs. Enables software development before FPGA build is ready.

### SynAI HiFi + Lx7 Multi-Core Runtime (Synaptics)
Implemented custom features in TensorFlow runtime on HiFi core. Created custom SynAI operator support in TensorFlow runtime. Developed and maintained SynAI multicore mailbox driver between host MCU and NPU. Developed firmware for uNPU on Lx7 core receiving operator info from HiFi core via interrupt and calling specialized kernel functions.

### Multi-Model Support (Synaptics)
Complete ownership of compiler and runtime features to run multiple tflite models. Designed and developed a mechanism to switch between models in external memory by splitting models into chunks and loading only what's needed — reduced model-switching delay by making use of max available chip memory.

### Multi-Core Timeline (ETA Compute)
Proposed and implemented a timeline logger and viewer showing how multiple cores are utilized at runtime. Gave deep insight into core under-utilization and helped adjust load balancing. Played a crucial role in winning a customer.

### Edge AI Compiler (Synaptics / ETA Compute)
A compiler that converts TensorFlow tflite model files into C files compilable with the AI runtime code. Parses tflite and generates optimized kernel calls for each operator's parameters.

### Mortise Smart Lock (OYO)
Smart lock for mortise doors — unlockable via BLE app and touch keypad. Supports OTA, activity log upload, offline operation via TOTP. Estimated 1.5+ year battery backup (10 lock/unlock cycles/day, 4 AA batteries).

### AWS IoT Gateway (OYO)
Gateway device bridging BT devices and AWS server, transparently — server unaware of the gateway, removing server-side coding dependency. Role: Project Lead (FW and HW), design and execution.

### Platform Design (OYO)
Designed a common codebase platform across products for higher code reusability and shorter time to market.

### Auto ROM Abandoning Patch Mechanism (Broadcom)
Detects symbols modified from ROM using MD5 checksum comparison of ASM files and automatically creates patch entries. All modified symbols moved from ROM to RAM.

### Bluetooth RF Firmware Development – Audio Features (Broadcom)
Implemented new features, bug fixing and maintenance of Bluetooth RF firmware. Boot Cosim analysis for tapeout readiness. Bringup of 4 Bluetooth chip projects. Sole ownership on 3+ RF firmware features improving audio quality.

### Push To Talk Radio Over Multicast IP Network (VVDN)
Xilinx Zynq-7000 based system with push-to-talk over multicast IP network using GStreamer.

### Low Speed Signal Generator / Data Acquisition System (SFO)
FreeRTOS based device generating Analog, GPIO, UART, SPI, I2C signals based on time-based or real-time event-based inputs via PC software.

### X-Ray Starter (SFO)
Multi-controller project controlling and monitoring X-Ray Anode based on host configuration.

### Power Line Communication Modem (SFO)
PIC32 based UART-PLC communication modem with data rate up to 5kbps.

---

## Academic & Personal Projects

- **Scheduler from Scratch** — Simple cooperative scheduler switching between two tasks with all static memory
- **Motorbike Performance Tuner** — Ignition timing control add-on increasing power, mileage and top speed
- **Quad-Pie** — Quadcopter with Arduino-based control
- **Nokia 3310 Music Composer Clone** — Keypad, LCD & Speaker in 8051 Assembly Language

---

## Education

| Qualification | Institute | Board/University | Year |
|---------------|-----------|------------------|------|
| B.Tech | Govt. Rajiv Gandhi Institute of Technology | MG University, Kerala | 2012 |
