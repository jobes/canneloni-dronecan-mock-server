# ──────────────────────────────────────────────
# Cannelloni protocol constants
# ──────────────────────────────────────────────
CANNELLONI_VERSION = 2
CANNELLONI_OP_DATA = 0
CANNELLONI_HEADER_SIZE = 5

# ──────────────────────────────────────────────
# CAN constants
# ──────────────────────────────────────────────
CAN_EFF_FLAG = 0x80000000
CAN_EFF_MASK = 0x1FFFFFFF

# ──────────────────────────────────────────────
# DroneCAN / UAVCAN v0 constants
# ──────────────────────────────────────────────
DRONECAN_NODE_ID = 2
DRONECAN_NODE_NAME = "gateway.mock"
DRONECAN_NODESTATUS_DTID = 341
DRONECAN_GETNODEINFO_DTID = 1
DRONECAN_GETNODEINFO_SIGNATURE = 0xEE468A8121C46A9E
DRONECAN_PRIORITY_DEFAULT = 4

HEALTH_OK = 0
MODE_OPERATIONAL = 0
