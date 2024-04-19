# RS-485 for Home Assistant

Integrate specific RS-485 devices into Home Assistant via an RS-485 to TCP device.

## Installation

### HACS

This is the recommended method of installation.

1. Add this repository as a custom repository in HACS.
2. Search for and install the RS-485 Device integration from HACS.
3. Restart Home Assistant.

## Setup

From the Home Assistant Integrations page, search for and add the RS-485 Device integration.

## Specification

### Currently supports:
- RS-485 switch LP-F8
- Dooya curtain motor CMD82-5S

### How to use:

1. Enter the IP address and port of the RS-485 to TCP device.
2. Choose the type of device to add:
    - Switch
      - Device name
      - Slave address (decimal)
      - Number of buttons
      - Includes a relay for high voltage control
    -Curtain motor
      - Device name
      - Slave address (decimal)
      Default address is 0x12 0x34, so enter 4660.

Currently, only essential features have been developed; many functionalities are still to be implemented.
