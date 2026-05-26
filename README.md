# 🛰️ Cannelloni DroneCAN Mock Server

A modern, high-fidelity DroneCAN (UAVCAN v0) node simulator written in Python. It communicates via a UDP tunnel using the [Cannelloni](https://github.com/mguentner/cannelloni) protocol, allowing you to emulate real hardware behavior on a virtual CAN bus in Linux.

This simulator is designed for developers of avionics, autopilots, and control systems who need to test DroneCAN interfaces, monitoring tools (like the **DroneCAN GUI Tool**), or develop downstream software without needing physical CAN hardware.

---

## 🌟 Key Features

- **🔄 Bidirectional Communication:** Handles receiving and sending CAN frames encapsulated in Cannelloni UDP packets.
- **💓 DroneCAN Heartbeat:** Periodically broadcasts `uavcan.protocol.NodeStatus` messages with node status (Node Health, Mode, Uptime).
- **🛰️ GPX Flight Simulation (Fix2):** Loads a real flight path from a GPX file (`assets/flight.gpx`) and broadcasts complex `uavcan.equipment.gnss.Fix2` messages in real time (coordinates, altitude, 3D velocity, satellites, etc.).
- **🧬 Dynamic Node Allocation (DNA):** Supports the standard protocol for automatic Node ID assignment (`uavcan.protocol.dynamic_node_id.Allocation`).
- **ℹ️ Node Information:** Responds to `uavcan.protocol.GetNodeInfo` service requests and constructs valid multi-frame responses with node metadata.
- **🛡️ Socket-Free Python implementation:** The Python script communicates strictly via a UDP network socket, meaning it requires no native SocketCAN C-libraries or complex Python wrapper setups to run.

---

## 📐 Architecture Overview

The entire infrastructure consists of three cooperating layers:

1. **Virtual Bus (`vcan0`):** A local Linux SocketCAN interface that client applications and diagnostic tools connect to.
2. **Cannelloni Bridge Daemon:** A C++ daemon that acts as a bridge – passing CAN frames between `vcan0` and a UDP port back and forth.
3. **Mock Server (Python):** This application, which runs on a UDP port and handles/generates DroneCAN protocols internally.

```text
┌────────────────────┐            ┌─────────┐            ┌───────────────┐            ┌────────────────────┐
│  DroneCAN GUI      │ ◄──(CAN)──►│  vcan0  │ ◄──(CAN)──►│  Cannelloni   │ ◄──(UDP)──►│ Python Mock Server │
│  (or autopilot)    │            │ (Linux) │            │ (Bridge Daemon│            │   (Port 20001)     │
└────────────────────┘            └─────────┘            └───────────────┘            └────────────────────┘
```

---

## 📋 Prerequisites

To run the system successfully, you will need:

- **Linux OS** (required for the `vcan` kernel module)
- **Python 3.8+**
- **Cannelloni Daemon** (installed via your package manager or compiled from [source](https://github.com/mguentner/cannelloni))
- Python dependencies (e.g., `pyyaml` and `zeroconf` for mDNS)

---

## 🚀 Quick Start & Setup Guide

### 1. Create a Virtual CAN Interface (`vcan0`)

Load the virtual CAN kernel module and create the `vcan0` interface:

```bash
# Load the virtual CAN module into the Linux kernel
sudo modprobe vcan

# Add a new virtual CAN network interface named vcan0
sudo ip link add dev vcan0 type vcan

# Bring the interface up
sudo ip link set up vcan0
```

### 2. Run the Cannelloni Bridge

Start the `cannelloni` daemon to bridge `vcan0` with UDP ports.

```bash
cannelloni -I vcan0 -R 127.0.0.1 -r 20001 -l 20000
```
*Tip: Keep this command running in a separate terminal window or run it in the background.*

### 3. Run the DroneCAN Mock Server

Start the main Python script:

```bash
python3 main.py
```

Upon successful startup, a clean dashboard showing the node status will appear in the terminal, and the application will wait for the first incoming packet (the client).

---

## 🛠️ Configuration

You can customize the simulated node's behavior and properties in the `config.yaml` file.

```yaml
# Cannelloni DroneCAN Mock Node Configuration
node_id: 2                      # Default node ID (0 for dynamic assignment via DNA)
node_name: "gateway.mock"       # Node name sent in GetNodeInfo
priority: 4                     # Message priority (0-7, where 0 is highest)
heartbeat_interval: 1.0         # Heartbeat broadcast interval in seconds
gpx: "assets/flight.gpx"        # Path to the GPX flight track file for the GPS simulator
local_port: 20001               # Local UDP port for Cannelloni communication
```

To run with a custom configuration file:
```bash
python3 main.py --config path/to/my_config.yaml
```

---

## 📺 Connecting to the DroneCAN GUI Tool

To visualize and interact with our simulated node:

1. Launch the **[DroneCAN GUI Tool](https://dronecan.github.io/GUI_Tool/)**. You can easily run it without global installation using `uv`:
   ```bash
   uv run --python 3.10 --with setuptools --with PyQt5 --with "qtawesome<1.1.0" --with dronecan_gui_tool dronecan_gui_tool
   ```
2. In the **Interface Selection** window:
   - Select **SocketCAN** as the interface type.
   - Choose **`vcan0`** from the interface name dropdown list.
   - You can leave the Bit Rate settings at their default values (the virtual interface ignores them).
3. Click **OK**.
4. **In the GUI, you will immediately see:**
   - The node named `gateway.mock` highlighted green in the node directory list.
   - In the local bus monitor, you will see a constant stream of `uavcan.equipment.gnss.Fix2` messages updating the position in real time based on the GPX path.
   - Double-clicking the node triggers a `GetNodeInfo` service request to verify all metadata response values.

---

## 📁 Project Structure

- `main.py` - Application entry point, handling UDP sockets and managing asynchronous tasks.
- `node.py` - Core logic of the simulated DroneCAN node, binding publishers and service handlers.
- `cannelloni.py` - Encapsulation and decapsulation of CAN frames from/into Cannelloni UDP packets.
- `dronecan.py` - Low-level DroneCAN message serialization and bit packing.
- `reassembler.py` - Reassembles multi-frame transfers from incoming CAN transport frames.
- `publishers/` - Components responsible for generating and broadcasting periodic messages (Heartbeat, GNSS GPS).
- `services/` - Service handlers for processing incoming requests (GetNodeInfo).
- `assets/` - Static assets, including flight routes in GPX format.
