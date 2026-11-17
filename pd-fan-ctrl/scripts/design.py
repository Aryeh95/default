"""PD fan controller, rev B: parts, nets and placement.

Seeed XIAO ESP32-C6 on two surface-mount 1x7 sockets; everything else surface-mount.

Changes from Rev A
  - 5 V rail: second TPS54302 buck (surface mount) instead of the K7805 SIP module
  - 12 V inductor: TMPA0605S-150MN-D (15 uH, 4 A, in stock at JLCPCB) on its EasyEDA land pattern
  - FAN2 tach read on its own pin (GPIO20) with its own pull-up and series resistor
  - tach series resistors 10 k (protects the GPIO from fans that pull tach up to 12 V)
  - 5 V inductor rated 3 A saturation (FXL0518), VBUS test pad TP1
  - fan-header peg holes 1.3 mm (Molex recommends 1.25 mm) for machine insertion
  - 16-pin USB-C socket (its data lines are unused)
"""


FP = "/usr/share/kicad/footprints/"

R0603 = ("Resistor_SMD", "R_0603_1608Metric")
R1206 = ("Resistor_SMD", "R_1206_3216Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
C1206 = ("Capacitor_SMD", "C_1206_3216Metric")
SOT23 = ("Package_TO_SOT_SMD", "SOT-23")
TSOT6 = ("Package_TO_SOT_SMD", "TSOT-23-6")
HDR4 = ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical")
FAN4 = ("Connector", "FanPinHeader_1x04_P2.54mm_Vertical")

BOARD_W, BOARD_H = 52.0, 46.0

# ref: (footprint, value, (x, y, rot), {pad: net}, lcsc, assembled_by_jlc, symbol)
PARTS = {
    # --- USB-C input (16-pin; D+/D- unused) ---------------------------------
    "J1": (("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12"), "USB-C 16P TYPE-C-31-M-12",
           (3.25, 14.0, -90),
           {"A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND", "S1": "GND",
            "A4": "VBUS", "B4": "VBUS", "A9": "VBUS", "B9": "VBUS",
            "A5": "CC_A", "B5": "CC_B"}, "C165948", True, "custom:USB_C_16P"),
    # --- USB PD sink -------------------------------------------------------
    "U1": (("Package_SO", "SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm"), "CH224A",
           (13.0, 9.6, -90),
           {"1": "VHV", "2": "SCL", "3": "SDA", "4": "DPDM", "5": "DPDM", "6": "CC_A", "7": "CC_B", "8": "VBUS_DET",
            "9": "CFG1", "10": "PD_PG", "11": "GND"}, "C42459160", True, "custom:CH224A"),
    "R1": (R1206, "0R", (18.6, 8.6, 180), {"1": "VBUS", "2": "VHV"}, "C17888", True, "Device:R"),
    "C1": (C0603, "1uF 50V", (18.0, 6.4, 0), {"1": "VHV", "2": "GND"}, "C15849", True, "Device:C"),
    "R16": (R0603, "0R", (13.0, 14.9, 90), {"1": "VBUS", "2": "VBUS_DET"}, "C21189", True, "Device:R"),
    "R2": (R0603, "56k", (14.6, 14.9, 90), {"1": "GND", "2": "CFG1"}, "C23206", True, "Device:R"),
    # --- VBUS voltage sense ------------------------------------------------
    "R11": (R0603, "100k", (20.5, 19.2, 0), {"1": "VBUS", "2": "VSENSE"}, "C25803", True, "Device:R"),
    "R12": (R0603, "15k", (20.5, 21.0, 0), {"1": "GND", "2": "VSENSE"}, "C22809", True, "Device:R"),
    "C7": (C0603, "100nF 50V", (17.4, 21.0, 0), {"1": "GND", "2": "VSENSE"}, "C14663", True, "Device:C"),
    # --- 12 V fan rail: TPS54302 buck -------------------------------------
    "U4": (TSOT6, "TPS54302", (8.5, 27.0, 180),
           {"1": "GND", "2": "SW", "3": "VBUS", "4": "FB", "5": "BUCK_EN", "6": "BOOT"},
           "C311983", True, "custom:TPS54302"),
    "C9": (C1206, "10uF 50V", (11.9, 27.0, 90), {"1": "GND", "2": "VBUS"}, "C13585", True, "Device:C"),
    "C10": (C0603, "100nF 50V", (10.4, 23.9, 0), {"1": "VBUS", "2": "GND"}, "C14663", True, "Device:C"),
    "C8": (C0603, "100nF 50V", (8.5, 30.1, 0), {"1": "BOOT", "2": "SW"}, "C14663", True, "Device:C"),
    "L1": (("custom", "L_TMPA0605S"), "15uH 4A TMPA0605S-150MN-D", (17.8, 27.0, 0),
           {"1": "SW", "2": "+12V"}, "C305194", True, "Device:L"),
    "C11": (C1206, "22uF 25V", (24.9, 24.3, 0), {"1": "+12V", "2": "GND"}, "C12891", True, "Device:C"),
    "C12": (C1206, "22uF 25V", (24.9, 27.0, 0), {"1": "+12V", "2": "GND"}, "C12891", True, "Device:C"),
    "C13": (C1206, "22uF 25V", (24.9, 29.7, 0), {"1": "+12V", "2": "GND"}, "C12891", True, "Device:C"),
    "R3": (R0603, "100k", (4.6, 24.3, 0), {"1": "+12V", "2": "FB"}, "C25803", True, "Device:R"),
    "C6": (C0603, "100pF", (4.6, 22.5, 0), {"1": "+12V", "2": "FB"}, "C14858", True, "Device:C"),
    "R4": (R0603, "5.1k", (4.6, 26.05, 0), {"1": "GND", "2": "FB"}, "C23186", True, "Device:R"),
    "R6": (R0603, "100k", (4.6, 27.9, 0), {"1": "GND", "2": "BUCK_EN"}, "C25803", True, "Device:R"),
    "R5": (R0603, "10k", (4.6, 29.7, 0), {"1": "FAN_EN", "2": "BUCK_EN"}, "C25804", True, "Device:R"),
    # --- 5 V rail: TPS54302 buck (EN left open = always on) ----------------
    "U5": (TSOT6, "TPS54302", (32.5, 29.0, 180),
           {"1": "GND", "2": "SW5", "3": "VBUS", "4": "FB5", "6": "BOOT5"},
           "C311983", True, "custom:TPS54302"),
    "C17": (C1206, "10uF 50V", (35.9, 29.0, 90), {"1": "GND", "2": "VBUS"}, "C13585", True, "Device:C"),
    "C23": (C0603, "100nF 50V", (33.64, 25.8, 90), {"1": "VBUS", "2": "GND"}, "C14663", True, "Device:C"),
    "C18": (C0603, "100nF 50V", (32.5, 31.6, 0), {"1": "BOOT5", "2": "SW5"}, "C14663", True, "Device:C"),
    "L2": (("Inductor_SMD", "L_Changjiang_FXL0518"), "10uH 3A FXL0518-100-M", (40.4, 29.0, 0),
           {"1": "SW5", "2": "+5V"}, "C475910", True, "Device:L"),
    "C19": (C1206, "22uF 25V", (44.8, 28.6, 90), {"1": "+5V", "2": "GND"}, "C12891", True, "Device:C"),
    "C20": (C1206, "22uF 25V", (40.1, 33.2, 180), {"1": "+5V", "2": "GND"}, "C12891", True, "Device:C"),
    "R19": (R0603, "100k", (28.8, 27.2, 0), {"1": "+5V", "2": "FB5"}, "C25803", True, "Device:R"),
    "C21": (C0603, "100pF", (28.8, 25.4, 0), {"1": "+5V", "2": "FB5"}, "C14858", True, "Device:C"),
    "R20": (R0603, "13k", (28.8, 29.0, 0), {"1": "GND", "2": "FB5"}, "C22797", True, "Device:R"),
    # --- test pad for the charger voltage ---------------------------------
    "TP1": (("TestPoint", "TestPoint_Pad_D1.5mm"), "VBUS", (18.0, 32.6, 0), {"1": "VBUS"}, "", False,
            "custom:TestPoint"),
    # --- fan PWM (open collector) and tach inputs --------------------------
    "Q3": (SOT23, "MMBT3904", (38.0, 38.5, 0), {"1": "Q3_B", "2": "GND", "3": "FAN_PWM"}, "C20526", True,
           "custom:NPN_BEC"),
    "R7": (R0603, "1k", (38.0, 35.5, 0), {"1": "PWM_MCU", "2": "Q3_B"}, "C21190", True, "Device:R"),
    "R8": (R0603, "100k", (38.0, 41.5, 180), {"1": "GND", "2": "Q3_B"}, "C25803", True, "Device:R"),
    "R9": (R0603, "10k", (42.5, 38.5, 0), {"1": "+3V3", "2": "FAN_TACH"}, "C25804", True, "Device:R"),
    "R10": (R0603, "10k", (42.5, 41.0, 180), {"1": "TACH_MCU", "2": "FAN_TACH"}, "C25804", True, "Device:R"),
    "R17": (R0603, "10k", (34.0, 34.4, 0), {"1": "+3V3", "2": "FAN2_TACH"}, "C25804", True, "Device:R"),
    "R18": (R0603, "10k", (34.0, 36.2, 180), {"1": "TACH2_MCU", "2": "FAN2_TACH"}, "C25804", True, "Device:R"),
    # --- connectors (hand-soldered fan headers) ----------------------------
    "J2": (FAN4, "Molex 47053-1000", (12.0, 41.0, 0),
           {"1": "GND", "2": "+12V", "3": "FAN_TACH", "4": "FAN_PWM"}, "C240840", False,
           "custom:Fan_4pin"),
    "J3": (FAN4, "Molex 47053-1000", (25.0, 41.0, 0),
           {"1": "GND", "2": "+12V", "3": "FAN2_TACH", "4": "FAN_PWM"}, "C240840", False,
           "custom:Fan_4pin"),
    "J4": (HDR4, "I2C", (48.5, 17.0, 0),
           {"1": "GND", "2": "+3V3", "3": "SDA", "4": "SCL"}, "", False, "custom:Header_I2C"),
    "J5": (HDR4, "UART", (48.5, 29.0, 0),
           {"1": "GND", "2": "+5V", "3": "UART_RX", "4": "UART_TX"}, "", False, "custom:Header_UART"),
    "R14": (R0603, "4.7k", (42.8, 23.6, 0), {"1": "+3V3", "2": "SDA"}, "C23162", True, "Device:R"),
    "R15": (R0603, "4.7k", (42.8, 25.4, 0), {"1": "+3V3", "2": "SCL"}, "C23162", True, "Device:R"),
}

# XIAO pin -> net (pins 1-7 down the left row, 8-14 up the right row)
XIAO_NETS = {1: "VSENSE", 2: "FAN_EN", 3: "PWM_MCU", 4: "PD_PG", 5: "SDA", 6: "SCL", 7: "UART_TX",
             8: "UART_RX", 9: "TACH_MCU", 10: "TACH2_MCU", 12: "+3V3", 13: "GND", 14: "XIAO_5V"}
XIAO_X, XIAO_Y = 33.5, 11.5

PARTS.update({
    # sockets: J6 pin k = XIAO pin k; J7 pin k = XIAO pin 15-k (pin 1 of both at the top)
    "J6": (("custom", "SOCKET_1x7_SMD"), "1x7 female header SMD 5mm PM2.54-1x7PLT-H5.0-R",
           (XIAO_X - 7.62, XIAO_Y, -90),
           {str(k): XIAO_NETS[k] for k in range(1, 8) if k in XIAO_NETS}, "C55218891", True,
           "custom:Socket_1x7"),
    "J7": (("custom", "SOCKET_1x7_SMD"), "1x7 female header SMD 5mm PM2.54-1x7PLT-H5.0-R",
           (XIAO_X + 7.62, XIAO_Y, -90),
           {str(k): XIAO_NETS[15 - k] for k in range(1, 8) if (15 - k) in XIAO_NETS}, "C55218891", True,
           "custom:Socket_1x7"),
    "D1": (("Diode_SMD", "D_SMA"), "SS14", (46.6, 10.6, 90), {"1": "XIAO_5V", "2": "+5V"}, "C2480", True,
           "Device:D_Schottky"),
    "C4": (C0603, "100nF 50V", (41.6, 21.6, 0), {"1": "+3V3", "2": "GND"}, "C14663", True, "Device:C"),
})
# copper keep-out under the XIAO's chip antenna (x0, y0, x1, y1)
ANT_KEEPOUT = (XIAO_X - 5.5, 17.6, XIAO_X + 5.5, 24.5)
HOLES = [(3.5, 3.5), (48.5, 3.5), (3.5, 42.5), (48.5, 42.5)]

# net classes: (track width, clearance, via dia, via drill)
POWER_NETS = ["VBUS", "+12V", "SW", "SW5"]
MID_NETS = ["+5V", "XIAO_5V", "+3V3", "GND", "VHV"]
CLASSES = {
    "Default": (0.25, 0.2, 0.7, 0.3),
    "Power": (0.8, 0.2, 0.9, 0.5),
    "Mid": (0.5, 0.2, 0.8, 0.4),
}
