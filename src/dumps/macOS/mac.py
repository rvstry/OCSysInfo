import asyncio
import binascii
import dumps.macOS.ioreg as ioreg
import subprocess

from managers.devicemanager import DeviceManager


class MacHardwareManager:
    """
    Instance, implementing `DeviceManager`, for extracting system information
    from macOS using the `IOKit` framework.

    https://developer.apple.com/documentation/iokit
    """

    def __init__(self, parent: DeviceManager):
        self.info = parent.info
        self.pci = parent.pci

    def dump(self):
        self.cpu_info()
        self.gpu_info()
        self.net_info()
        self.audio_info()

    def cpu_info(self):
        # Full list of features for this CPU.
        features = subprocess.getoutput('sysctl machdep.cpu.features')

        data = {
            # Amount of cores for this processor.
            'Cores': subprocess.getoutput('sysctl machdep.cpu.core_count').split(': ')[1] + " cores",

            # Amount of threads for this processor.
            'Threads': subprocess.getoutput('sysctl machdep.cpu.thread_count').split(': ')[1] + " threads"
        }

        if features:
            # Highest supported SSE version.
            data['SSE'] = sorted(list(filter(lambda f: 'sse' in f.lower(
            ) and not 'ssse' in f.lower(), features.split(': ')[1].split(' '))), reverse=True)[0]

            # Whether or not SSSE3 support is present.
            data['SSSE3'] = 'Supported' if features.lower().find(
                'ssse3') > -1 else 'Not Available'

        # Model of the CPU
        model = subprocess.getoutput(
            'sysctl -a | grep "brand_string"').split(': ')[1]

        self.info.get('CPU').append({
            model: data
        })

    def gpu_info(self):

        device = {
            'IOProviderClass': 'IOPCIDevice',
            # Bit mask matching, ensuring that the 3rd byte is one of the display controller (0x03).
            'IOPCIClassMatch': '0x03000000&0xff000000'
        }

        # Obtain generator instance, whose values are `CFDictionary`-ies
        interface = ioreg.ioiterator_to_list(ioreg.IOServiceGetMatchingServices(
            ioreg.kIOMasterPortDefault,
            device,
            None)[1])

        # Loop through the generator returned from `ioiterator_to_list()`
        for i in interface:

            # Obtain CFDictionaryRef of the current PCI device.
            device = ioreg.corefoundation_to_native(ioreg.IORegistryEntryCreateCFProperties(
                i, None, ioreg.kCFAllocatorDefault, ioreg.kNilOptions))[1]

            model = bytes(device.get('model')).decode()

            dev = (binascii.b2a_hex(
                bytes(reversed(device.get('device-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

            ven = (binascii.b2a_hex(
                bytes(reversed(device.get('vendor-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

            self.info.get('GPU').append({
                model: {
                    'Device ID': dev,
                    'Vendor': ven,
                }
            })

            ioreg.IOObjectRelease(i)

    def net_info(self):

        device = {
            'IOProviderClass': 'IOPCIDevice',
            # Bit mask matching, ensuring that the 3rd byte is one of the network controller (0x02).
            'IOPCIClassMatch': '0x02000000&0xff000000'
        }

        # Obtain generator instance, whose values are `CFDictionary`-ies
        interface = ioreg.ioiterator_to_list(ioreg.IOServiceGetMatchingServices(
            ioreg.kIOMasterPortDefault,
            device,
            None)[1])

        # Loop through the generator returned from `ioiterator_to_list()`
        for i in interface:

            # Obtain CFDictionaryRef of the current PCI device.
            device = ioreg.corefoundation_to_native(ioreg.IORegistryEntryCreateCFProperties(
                i, None, ioreg.kCFAllocatorDefault, ioreg.kNilOptions))[1]

            dev = (binascii.b2a_hex(
                bytes(reversed(device.get('device-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

            ven = (binascii.b2a_hex(
                bytes(reversed(device.get('vendor-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

            model = asyncio.run(self.pci.get_item(dev, ven))

            self.info.get('Network').append({
                model: {
                    'Device ID': dev,
                    'Vendor': ven,
                }
            })

            ioreg.IOObjectRelease(i)

    def audio_info(self, default=False):

        if default:
            _device = {
                'IOProviderClass': 'IOPCIDevice',
                # Bit mask matching, ensuring that the 3rd byte is one of the multimedia controller (0x04).
                'IOPCIClassMatch': '0x04000000&0xff000000'
            }
        else:
            _device = {'IOProviderClass': 'IOHDACodecDevice'}

        # Obtain generator instance, whose values are `CFDictionary`-ies
        interface = ioreg.ioiterator_to_list(ioreg.IOServiceGetMatchingServices(
            ioreg.kIOMasterPortDefault,
            _device,
            None)[1])

        # Loop through the generator returned from `ioiterator_to_list()`
        for i in interface:

            # Obtain CFDictionaryRef of the current PCI device.
            device = ioreg.corefoundation_to_native(ioreg.IORegistryEntryCreateCFProperties(
                i, None, ioreg.kCFAllocatorDefault, ioreg.kNilOptions))[1]

            if default == False:
                # Ensure it's the AppleHDACodec device
                if device.get('DigitalAudioCapabilities'):
                    continue

                ven = hex(device.get('IOHDACodecVendorID'))[2:6]
                dev = hex(device.get('IOHDACodecVendorID'))[6:]

                model = asyncio.run(self.pci.get_item(deviceID=dev, ven=ven))
            else:
                dev = (binascii.b2a_hex(
                    bytes(reversed(device.get('device-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

                ven = (binascii.b2a_hex(
                    bytes(reversed(device.get('vendor-id')))).decode()[4:])  # Reverse the byte sequence, and format it using `binascii` – remove leading 0s

                model = asyncio.run(self.pci.get_item(dev, ven))

            self.info.get('Audio').append({
                model: {
                    'Device ID': dev,
                    'Vendor': ven,
                }
            })

            ioreg.IOObjectRelease(i)

        # If we don't find any AppleHDACodec devices (i.e. if it's a T2 Mac, find any multimedia controllers.)
        if not self.info.get('Audio'):
            self.audio_info(default=True)