if [ $1 -eq 1 ]
then
	echo "Set the image size transmitted by VDMA to 1920x1080"
fi

if [ $1 -eq 2 ]
then
	echo "Set the image size transmitted by VDMA to 800x480"
fi

#Configure the Write channel registers
# S2MM VDMA Control Register
devmem 0x43000030 32 0x4 		 #reset
devmem 0x43000030 32 0x108B		 # enable circular mode
#S2MM Start addr
devmem 0x430000AC 32 0x1A000000  # start address
devmem 0x430000B0 32 0x1A800000  # start address
devmem 0x430000B4 32 0x1B000000  # start address

if [ $1 -eq 1 ]
then
	devmem 0x430000A8 32 7680    # h offset (1920 * 4) bytes
	devmem 0x430000A4 32 7680    # h size (1920 * 4) bytes
	devmem 0x430000A0 32 1080    # v size (1080) bytes
fi

if [ $1 -eq 2 ]
then
	devmem 0x430000A8 32 3200    # h offset (800 * 4) bytes
	devmem 0x430000A4 32 3200    # h size (800 * 4) bytes
	devmem 0x430000A0 32 480	 # v size (480) bytes
fi

#Configure the Read channel registers
# MM2S VDMA Control Register
devmem 0x43000000 32 0x4		 #reset
devmem 0x43000000 32 0x108B      # enable circular mode
#MM2S Start addr
devmem 0x4300005C 32 0x1A000000  # start address
devmem 0x43000060 32 0x1A800000  # start address
devmem 0x43000064 32 0x1B000000  # start address

if [ $1 -eq 1 ]
then
	devmem 0x43000058 32 7680    # h offset (1920 * 4) bytes
	devmem 0x43000054 32 7680    # h size (1920 * 4) bytes
	devmem 0x43000050 32 1080    # v size (1080) bytes
fi

if [ $1 -eq 2 ]
then
	devmem 0x43000058 32 3200    # h offset (800 * 4) bytes
	devmem 0x43000054 32 3200    # h size (800 * 4) bytes
	devmem 0x43000050 32 480	 # v size (480) bytes
fi
