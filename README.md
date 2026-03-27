# Cannelloni DroneCAN Mock Server

A Python-based mock server that simulates a DroneCAN (UAVCAN v0) node communicating over a UDP connection via the [Cannelloni](https://github.com/mguentner/cannelloni) protocol.

This mock server is useful for testing DroneCAN interfaces and GUI tools (like DroneCAN GUI Tool) without needing physical CAN hardware.

## Features

- **Bidirectional Communication:** Handles receiving requests and sending responses over Cannelloni UDP packets.
- **DroneCAN Heartbeat:** Broadcasts `uavcan.protocol.NodeStatus` heartbeat messages periodically to advertise its presence.
- **Node Information:** Responds to `uavcan.protocol.GetNodeInfo` service requests with node details (like node name, e.g., `gateway.mock` and uptime).
- **Socket-Free Mocking:** Does not require local SocketCAN bindings in Python; communicates strictly over UDP to a Cannelloni tunnel.

## Architecture

The system consists of three parts working together:
1. **vcan0:** A virtual CAN interface on your Linux machine.
2. **Cannelloni:** A C++ daemon that bridges CAN frames from `vcan0` to UDP packets.
3. **Mock Server:** This Python script, which sends and receives CAN frames encapsulated in UDP via Cannelloni.

```text
[ GUI Tool / Client ] <──(CAN)──> [ vcan0 ] <──(CAN)──> [ Cannelloni ] <──(UDP)──> [ Python Mock Server ]
```

## Prerequisites

- Python 3.6+
- Linux operating system (for `vcan` kernel module)
- `cannelloni` installed on your system (Available via standard package managers or compiled from source)

---

## 🚀 Setup & Usage Guide

### 1. How to make a Virtual CAN Interface (`vcan`)

First, you need to create a virtual CAN interface named `vcan0` to allow local DroneCAN tools to communicate.

Run the following commands in your terminal:

```bash
# Load the virtual CAN kernel module
sudo modprobe vcan

# Add a new virtual CAN network interface named vcan0
sudo ip link add dev vcan0 type vcan

# Bring the interface up
sudo ip link set up vcan0
```

### 2. How to run Cannelloni

Next, start Cannelloni to bridge the `vcan0` interface to UDP ports. 

By default, the mock server is configured to:
- Send UDP packets to Cannelloni on port `20000`.
- Receive UDP packets from Cannelloni on port `20001`.

Run Cannelloni with these matching ports:

```bash
cannelloni -I vcan0 -R 127.0.0.1 -r 20001 -l 20000
```
*Tip: Leave this running in a separate terminal or run it in the background.*

### 3. How to run the Mock Server

Once `vcan0` is up and `cannelloni` is running, you can start the mock server:

```bash
python3 main.py
```

It will immediately start broadcasting DroneCAN heartbeats. You can now open a DroneCAN diagnostic tool (like the official DroneCAN GUI Tool), connect it to `vcan0`, and you will see the mock node appear.

#### Command-Line Arguments

You can customize the mock server using the following arguments:

| Argument | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Remote IP where Cannelloni is running |
| `--remote-port` | `20000` | UDP port where Cannelloni is listening |
| `--local-port` | `20001` | UDP port this script binds to receive data |
| `--node-id` | *(varies)* | The DroneCAN Node ID for the simulation |
| `--node-name` | `gateway.mock` | Node name returned in GetNodeInfo |
| `--priority` | `4` | DroneCAN message priority |
| `--interval` | `1.0` | Heartbeat interval rate in seconds |

Example with custom arguments:
```bash
python3 main.py --node-id 42 --node-name custom.node --interval 0.5
```
