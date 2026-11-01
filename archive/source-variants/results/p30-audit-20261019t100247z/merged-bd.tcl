
################################################################
# This is a generated script based on design: system
#
# Though there are limitations about the generated script,
# the main purpose of this utility is to make learning
# IP Integrator Tcl commands easier.
################################################################

namespace eval _tcl {
proc get_script_folder {} {
   set script_path [file normalize [info script]]
   set script_folder [file dirname $script_path]
   return $script_folder
}
}
variable script_folder
set script_folder [_tcl::get_script_folder]

################################################################
# Check if script is running in correct Vivado version.
################################################################
set scripts_vivado_version 2021.1
set current_vivado_version [version -short]

if { [string first $scripts_vivado_version $current_vivado_version] == -1 } {
   puts ""
   catch {common::send_gid_msg -ssname BD::TCL -id 2041 -severity "ERROR" "This script was generated using Vivado <$scripts_vivado_version> and is being run in <$current_vivado_version> of Vivado. Please run the script in Vivado <$scripts_vivado_version> then open the design in Vivado <$current_vivado_version>. Upgrade the design by running \"Tools => Report => Report IP Status...\", then run write_bd_tcl to create an updated script."}

   return 1
}

################################################################
# START
################################################################

# To test this script, run the following commands from Vivado Tcl console:
# source system_script.tcl


# The design that will be created by this Tcl script contains the following 
# module references:
# dual_pixel_24bpp_lvds_mapping, lvds_n_x_7to1_sdr_tx

# Please add the sources of those modules before sourcing this Tcl script.

# If there is no project opened, this script will create a
# project, but make sure you do not have an existing project
# <./myproj/project_1.xpr> in the current working folder.

set list_projs [get_projects -quiet]
if { $list_projs eq "" } {
   create_project project_1 myproj -part xc7z100ffg900-2
}


# CHANGE DESIGN NAME HERE
variable design_name
set design_name system

# If you do not already have an existing IP Integrator design open,
# you can create a design using the following command:
#    create_bd_design $design_name

# Creating design if needed
set errMsg ""
set nRet 0

set cur_design [current_bd_design -quiet]
set list_cells [get_bd_cells -quiet]

if { ${design_name} eq "" } {
   # USE CASES:
   #    1) Design_name not set

   set errMsg "Please set the variable <design_name> to a non-empty value."
   set nRet 1

} elseif { ${cur_design} ne "" && ${list_cells} eq "" } {
   # USE CASES:
   #    2): Current design opened AND is empty AND names same.
   #    3): Current design opened AND is empty AND names diff; design_name NOT in project.
   #    4): Current design opened AND is empty AND names diff; design_name exists in project.

   if { $cur_design ne $design_name } {
      common::send_gid_msg -ssname BD::TCL -id 2001 -severity "INFO" "Changing value of <design_name> from <$design_name> to <$cur_design> since current design is empty."
      set design_name [get_property NAME $cur_design]
   }
   common::send_gid_msg -ssname BD::TCL -id 2002 -severity "INFO" "Constructing design in IPI design <$cur_design>..."

} elseif { ${cur_design} ne "" && $list_cells ne "" && $cur_design eq $design_name } {
   # USE CASES:
   #    5) Current design opened AND has components AND same names.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 1
} elseif { [get_files -quiet ${design_name}.bd] ne "" } {
   # USE CASES: 
   #    6) Current opened design, has components, but diff names, design_name exists in project.
   #    7) No opened design, design_name exists in project.

   set errMsg "Design <$design_name> already exists in your project, please set the variable <design_name> to another value."
   set nRet 2

} else {
   # USE CASES:
   #    8) No opened design, design_name not in project.
   #    9) Current opened design, has components, but diff names, design_name not in project.

   common::send_gid_msg -ssname BD::TCL -id 2003 -severity "INFO" "Currently there is no design <$design_name> in project, so creating one..."

   create_bd_design $design_name

   common::send_gid_msg -ssname BD::TCL -id 2004 -severity "INFO" "Making design <$design_name> as current_bd_design."
   current_bd_design $design_name

}

common::send_gid_msg -ssname BD::TCL -id 2005 -severity "INFO" "Currently the variable <design_name> is equal to \"$design_name\"."

if { $nRet != 0 } {
   catch {common::send_gid_msg -ssname BD::TCL -id 2006 -severity "ERROR" $errMsg}
   return $nRet
}

set bCheckIPsPassed 1
##################################################################
# CHECK IPs
##################################################################
set bCheckIPs 1
if { $bCheckIPs == 1 } {
   set list_check_ips "\ 
analog.com:user:axi_ad9361:1.0\
analog.com:user:axi_dmac:1.0\
analog.com:user:util_rfifo:1.0\
xilinx.com:ip:axi_vdma:6.3\
xilinx.com:ip:axis_subset_converter:1.1\
xilinx.com:ip:clk_wiz:6.0\
xilinx.com:ip:xlconstant:1.1\
xilinx.com:ip:proc_sys_reset:5.0\
xilinx.com:ip:smartconnect:1.0\
xilinx.com:ip:xlconcat:2.1\
xilinx.com:ip:processing_system7:5.5\
analog.com:user:util_wfifo:1.0\
analog.com:user:util_cpack:1.0\
analog.com:user:util_upack:1.0\
analog.com:user:util_clkdiv:1.0\
xilinx.com:ip:util_reduced_logic:2.0\
analog.com:user:util_tdd_sync:1.0\
xilinx.com:ip:v_axi4s_vid_out:4.0\
xilinx.com:ip:v_tc:6.2\
xilinx.com:ip:v_tpg:8.1\
xilinx.com:ip:xlslice:1.0\
"

   set list_ips_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2011 -severity "INFO" "Checking if the following IPs exist in the project's IP catalog: $list_check_ips ."

   foreach ip_vlnv $list_check_ips {
      set ip_obj [get_ipdefs -all $ip_vlnv]
      if { $ip_obj eq "" } {
         lappend list_ips_missing $ip_vlnv
      }
   }

   if { $list_ips_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2012 -severity "ERROR" "The following IPs are not found in the IP Catalog:\n  $list_ips_missing\n\nResolution: Please add the repository containing the IP(s) to the project." }
      set bCheckIPsPassed 0
   }

}

##################################################################
# CHECK Modules
##################################################################
set bCheckModules 1
if { $bCheckModules == 1 } {
   set list_check_mods "\ 
dual_pixel_24bpp_lvds_mapping\
lvds_n_x_7to1_sdr_tx\
"

   set list_mods_missing ""
   common::send_gid_msg -ssname BD::TCL -id 2020 -severity "INFO" "Checking if the following modules exist in the project's sources: $list_check_mods ."

   foreach mod_vlnv $list_check_mods {
      if { [can_resolve_reference $mod_vlnv] == 0 } {
         lappend list_mods_missing $mod_vlnv
      }
   }

   if { $list_mods_missing ne "" } {
      catch {common::send_gid_msg -ssname BD::TCL -id 2021 -severity "ERROR" "The following module(s) are not found in the project: $list_mods_missing" }
      common::send_gid_msg -ssname BD::TCL -id 2022 -severity "INFO" "Please add source files for the missing module(s) above."
      set bCheckIPsPassed 0
   }
}

if { $bCheckIPsPassed != 1 } {
  common::send_gid_msg -ssname BD::TCL -id 2023 -severity "WARNING" "Will not continue with creation of design due to the error(s) above."
  return 3
}

##################################################################
# DESIGN PROCs
##################################################################



# Procedure to create entire design; Provide argument to make
# procedure reusable. If parentCell is "", will use root.
proc create_root_design { parentCell } {

  variable script_folder
  variable design_name

  if { $parentCell eq "" } {
     set parentCell [get_bd_cells /]
  }

  # Get object for parentCell
  set parentObj [get_bd_cells $parentCell]
  if { $parentObj == "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2090 -severity "ERROR" "Unable to find parent cell <$parentCell>!"}
     return
  }

  # Make sure parentObj is hier blk
  set parentType [get_property TYPE $parentObj]
  if { $parentType ne "hier" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2091 -severity "ERROR" "Parent <$parentObj> has TYPE = <$parentType>. Expected to be <hier>."}
     return
  }

  # Save current instance; Restore later
  set oldCurInst [current_bd_instance .]

  # Set parent object as current
  current_bd_instance $parentObj


  # Create interface ports
  set ddr [ create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 ddr ]

  set fixed_io [ create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 fixed_io ]


  # Create ports
  set SPI0_MISO_I [ create_bd_port -dir I SPI0_MISO_I ]
  set SPI0_MOSI_O [ create_bd_port -dir O SPI0_MOSI_O ]
  set SPI0_SCLK_O [ create_bd_port -dir O SPI0_SCLK_O ]
  set SPI0_SS_O [ create_bd_port -dir O SPI0_SS_O ]
  set enable [ create_bd_port -dir O enable ]
  set gpio_i [ create_bd_port -dir I -from 63 -to 0 gpio_i ]
  set gpio_o [ create_bd_port -dir O -from 63 -to 0 gpio_o ]
  set gpio_t [ create_bd_port -dir O -from 63 -to 0 gpio_t ]
  set lcd_data_b [ create_bd_port -dir O -from 4 -to 0 lcd_data_b ]
  set lcd_data_g [ create_bd_port -dir O -from 5 -to 0 lcd_data_g ]
  set lcd_data_r [ create_bd_port -dir O -from 4 -to 0 lcd_data_r ]
  set lcd_de [ create_bd_port -dir O lcd_de ]
  set lcd_hsync [ create_bd_port -dir O lcd_hsync ]
  set lcd_pclk [ create_bd_port -dir O lcd_pclk ]
  set lcd_pwm_backlight [ create_bd_port -dir O lcd_pwm_backlight ]
  set lcd_vsync [ create_bd_port -dir O lcd_vsync ]
  set lvds_clk_out_n [ create_bd_port -dir O -from 1 -to 0 lvds_clk_out_n ]
  set lvds_clk_out_p [ create_bd_port -dir O -from 1 -to 0 lvds_clk_out_p ]
  set lvds_data_out_n [ create_bd_port -dir O -from 7 -to 0 lvds_data_out_n ]
  set lvds_data_out_p [ create_bd_port -dir O -from 7 -to 0 lvds_data_out_p ]
  set o_video_data [ create_bd_port -dir O -from 23 -to 0 o_video_data ]
  set o_video_de [ create_bd_port -dir O o_video_de ]
  set o_video_hsync [ create_bd_port -dir O o_video_hsync ]
  set o_video_pclk [ create_bd_port -dir O o_video_pclk ]
  set o_video_vsync [ create_bd_port -dir O o_video_vsync ]
  set rx_clk_in_n [ create_bd_port -dir I rx_clk_in_n ]
  set rx_clk_in_p [ create_bd_port -dir I rx_clk_in_p ]
  set rx_data_in_n [ create_bd_port -dir I -from 5 -to 0 rx_data_in_n ]
  set rx_data_in_p [ create_bd_port -dir I -from 5 -to 0 rx_data_in_p ]
  set rx_frame_in_n [ create_bd_port -dir I rx_frame_in_n ]
  set rx_frame_in_p [ create_bd_port -dir I rx_frame_in_p ]
  set spi1_clk_i [ create_bd_port -dir I spi1_clk_i ]
  set spi1_clk_o [ create_bd_port -dir O spi1_clk_o ]
  set spi1_csn_0_o [ create_bd_port -dir O spi1_csn_0_o ]
  set spi1_csn_1_o [ create_bd_port -dir O spi1_csn_1_o ]
  set spi1_csn_2_o [ create_bd_port -dir O spi1_csn_2_o ]
  set spi1_csn_i [ create_bd_port -dir I spi1_csn_i ]
  set spi1_sdi_i [ create_bd_port -dir I spi1_sdi_i ]
  set spi1_sdo_i [ create_bd_port -dir I spi1_sdo_i ]
  set spi1_sdo_o [ create_bd_port -dir O spi1_sdo_o ]
  set tdd_sync_i [ create_bd_port -dir I tdd_sync_i ]
  set tdd_sync_o [ create_bd_port -dir O tdd_sync_o ]
  set tdd_sync_t [ create_bd_port -dir O tdd_sync_t ]
  set tx_clk_out_n [ create_bd_port -dir O tx_clk_out_n ]
  set tx_clk_out_p [ create_bd_port -dir O tx_clk_out_p ]
  set tx_data_out_n [ create_bd_port -dir O -from 5 -to 0 tx_data_out_n ]
  set tx_data_out_p [ create_bd_port -dir O -from 5 -to 0 tx_data_out_p ]
  set tx_frame_out_n [ create_bd_port -dir O tx_frame_out_n ]
  set tx_frame_out_p [ create_bd_port -dir O tx_frame_out_p ]
  set txnrx [ create_bd_port -dir O txnrx ]
  set up_enable [ create_bd_port -dir I up_enable ]
  set up_txnrx [ create_bd_port -dir I up_txnrx ]

  # Create instance: axi_ad9361, and set properties
  set axi_ad9361 [ create_bd_cell -type ip -vlnv analog.com:user:axi_ad9361:1.0 axi_ad9361 ]
  set_property -dict [ list \
   CONFIG.ADC_INIT_DELAY {20} \
   CONFIG.ID {0} \
 ] $axi_ad9361

  # Create instance: axi_ad9361_adc_dma, and set properties
  set axi_ad9361_adc_dma [ create_bd_cell -type ip -vlnv analog.com:user:axi_dmac:1.0 axi_ad9361_adc_dma ]
  set_property -dict [ list \
   CONFIG.AXI_SLICE_DEST {false} \
   CONFIG.AXI_SLICE_SRC {false} \
   CONFIG.CYCLIC {false} \
   CONFIG.DMA_2D_TRANSFER {false} \
   CONFIG.DMA_AXI_PROTOCOL_DEST {1} \
   CONFIG.DMA_AXI_PROTOCOL_SRC {1} \
   CONFIG.DMA_DATA_WIDTH_SRC {64} \
   CONFIG.DMA_TYPE_DEST {0} \
   CONFIG.DMA_TYPE_SRC {2} \
   CONFIG.SYNC_TRANSFER_START {true} \
 ] $axi_ad9361_adc_dma

  # Create instance: axi_ad9361_dac_dma, and set properties
  set axi_ad9361_dac_dma [ create_bd_cell -type ip -vlnv analog.com:user:axi_dmac:1.0 axi_ad9361_dac_dma ]
  set_property -dict [ list \
   CONFIG.AXI_SLICE_DEST {true} \
   CONFIG.AXI_SLICE_SRC {false} \
   CONFIG.CYCLIC {true} \
   CONFIG.DMA_2D_TRANSFER {false} \
   CONFIG.DMA_AXI_PROTOCOL_DEST {1} \
   CONFIG.DMA_AXI_PROTOCOL_SRC {1} \
   CONFIG.DMA_DATA_WIDTH_DEST {64} \
   CONFIG.DMA_TYPE_DEST {2} \
   CONFIG.DMA_TYPE_SRC {0} \
 ] $axi_ad9361_dac_dma

  # Create instance: axi_ad9361_dac_fifo, and set properties
  set axi_ad9361_dac_fifo [ create_bd_cell -type ip -vlnv analog.com:user:util_rfifo:1.0 axi_ad9361_dac_fifo ]
  set_property -dict [ list \
   CONFIG.DIN_ADDRESS_WIDTH {4} \
   CONFIG.DIN_DATA_WIDTH {16} \
   CONFIG.DOUT_DATA_WIDTH {16} \
 ] $axi_ad9361_dac_fifo

  # Create instance: axi_cpu_interconnect, and set properties
  set axi_cpu_interconnect [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_cpu_interconnect ]
  set_property -dict [ list \
   CONFIG.NUM_MI {8} \
 ] $axi_cpu_interconnect

  # Create instance: axi_hp1_interconnect, and set properties
  set axi_hp1_interconnect [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_hp1_interconnect ]
  set_property -dict [ list \
   CONFIG.NUM_MI {1} \
   CONFIG.NUM_SI {1} \
 ] $axi_hp1_interconnect

  # Create instance: axi_hp2_interconnect, and set properties
  set axi_hp2_interconnect [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_hp2_interconnect ]
  set_property -dict [ list \
   CONFIG.NUM_MI {1} \
   CONFIG.NUM_SI {1} \
 ] $axi_hp2_interconnect

  # Create instance: axi_vdma_0, and set properties
  set axi_vdma_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_0 ]
  set_property -dict [ list \
   CONFIG.c_m_axis_mm2s_tdata_width {32} \
   CONFIG.c_mm2s_max_burst_length {16} \
   CONFIG.c_s2mm_max_burst_length {16} \
 ] $axi_vdma_0

  # Create instance: axis_subset_converter_0, and set properties
  set axis_subset_converter_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_subset_converter:1.1 axis_subset_converter_0 ]
  set_property -dict [ list \
   CONFIG.M_HAS_TKEEP {1} \
   CONFIG.M_HAS_TLAST {1} \
   CONFIG.M_HAS_TREADY {1} \
   CONFIG.M_HAS_TSTRB {1} \
   CONFIG.M_TDATA_NUM_BYTES {4} \
   CONFIG.M_TDEST_WIDTH {1} \
   CONFIG.M_TID_WIDTH {1} \
   CONFIG.M_TUSER_WIDTH {1} \
   CONFIG.S_HAS_TKEEP {1} \
   CONFIG.S_HAS_TLAST {1} \
   CONFIG.S_HAS_TREADY {1} \
   CONFIG.S_HAS_TSTRB {1} \
   CONFIG.S_TDATA_NUM_BYTES {3} \
   CONFIG.S_TDEST_WIDTH {1} \
   CONFIG.S_TID_WIDTH {1} \
   CONFIG.S_TUSER_WIDTH {1} \
   CONFIG.TDATA_REMAP {8'b0,tdata[23:16],tdata[7:0],tdata[15:8]} \
   CONFIG.TDEST_REMAP {tdest[0:0]} \
   CONFIG.TID_REMAP {tid[0:0]} \
   CONFIG.TKEEP_REMAP {1'b1,tkeep[2:0]} \
   CONFIG.TLAST_REMAP {tlast[0]} \
   CONFIG.TSTRB_REMAP {1'b1,tstrb[2:0]} \
   CONFIG.TUSER_REMAP {tuser[0:0]} \
 ] $axis_subset_converter_0

  # Create instance: axis_subset_converter_1, and set properties
  set axis_subset_converter_1 [ create_bd_cell -type ip -vlnv xilinx.com:ip:axis_subset_converter:1.1 axis_subset_converter_1 ]
  set_property -dict [ list \
   CONFIG.M_HAS_TKEEP {1} \
   CONFIG.M_HAS_TLAST {1} \
   CONFIG.M_HAS_TREADY {1} \
   CONFIG.M_HAS_TSTRB {0} \
   CONFIG.M_TDATA_NUM_BYTES {3} \
   CONFIG.M_TDEST_WIDTH {0} \
   CONFIG.M_TID_WIDTH {0} \
   CONFIG.M_TUSER_WIDTH {1} \
   CONFIG.S_HAS_TKEEP {1} \
   CONFIG.S_HAS_TLAST {1} \
   CONFIG.S_HAS_TREADY {1} \
   CONFIG.S_HAS_TSTRB {0} \
   CONFIG.S_TDATA_NUM_BYTES {4} \
   CONFIG.S_TDEST_WIDTH {0} \
   CONFIG.S_TID_WIDTH {0} \
   CONFIG.S_TUSER_WIDTH {1} \
   CONFIG.TDATA_REMAP {tdata[23:0]} \
   CONFIG.TKEEP_REMAP {tkeep[2:0]} \
   CONFIG.TLAST_REMAP {tlast[0]} \
   CONFIG.TUSER_REMAP {tuser[0:0]} \
 ] $axis_subset_converter_1

  # Create instance: clk_wiz_0, and set properties
  set clk_wiz_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_0 ]
  set_property -dict [ list \
   CONFIG.CLKIN1_JITTER_PS {100.0} \
   CONFIG.CLKOUT1_JITTER {217.614} \
   CONFIG.CLKOUT1_PHASE_ERROR {245.344} \
   CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {148.5} \
   CONFIG.CLKOUT2_JITTER {335.685} \
   CONFIG.CLKOUT2_PHASE_ERROR {479.985} \
   CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {100.000} \
   CONFIG.CLKOUT2_USED {false} \
   CONFIG.MMCM_CLKFBOUT_MULT_F {37.125} \
   CONFIG.MMCM_CLKIN1_PERIOD {10.000} \
   CONFIG.MMCM_CLKIN2_PERIOD {10.000} \
   CONFIG.MMCM_CLKOUT0_DIVIDE_F {6.250} \
   CONFIG.MMCM_CLKOUT1_DIVIDE {1} \
   CONFIG.MMCM_DIVCLK_DIVIDE {4} \
   CONFIG.NUM_OUT_CLKS {1} \
   CONFIG.PRIM_IN_FREQ {100.000} \
   CONFIG.USE_DYN_RECONFIG {true} \
   CONFIG.USE_LOCKED {true} \
   CONFIG.USE_RESET {true} \
 ] $clk_wiz_0

  # Create instance: dual_pixel_24bpp_lvds_mapping_0, and set properties
  set block_name dual_pixel_24bpp_lvds_mapping
  set block_cell_name dual_pixel_24bpp_lvds_mapping_0
  if { [catch {set dual_pixel_24bpp_lvds_mapping_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $dual_pixel_24bpp_lvds_mapping_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: integration_one, and set properties
  set integration_one [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 integration_one ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {1} \
 ] $integration_one

  # Create instance: integration_zero, and set properties
  set integration_zero [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 integration_zero ]
  set_property -dict [ list \
   CONFIG.CONST_VAL {0} \
 ] $integration_zero

  # Create instance: lvds_n_x_7to1_sdr_tx_0, and set properties
  set block_name lvds_n_x_7to1_sdr_tx
  set block_cell_name lvds_n_x_7to1_sdr_tx_0
  if { [catch {set lvds_n_x_7to1_sdr_tx_0 [create_bd_cell -type module -reference $block_name $block_cell_name] } errmsg] } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2095 -severity "ERROR" "Unable to add referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   } elseif { $lvds_n_x_7to1_sdr_tx_0 eq "" } {
     catch {common::send_gid_msg -ssname BD::TCL -id 2096 -severity "ERROR" "Unable to referenced block <$block_name>. Please add the files for ${block_name}'s definition into the project."}
     return 1
   }
  
  # Create instance: rst_clk_wiz_out, and set properties
  set rst_clk_wiz_out [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_clk_wiz_out ]

  # Create instance: rst_ps7_0_200M, and set properties
  set rst_ps7_0_200M [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_200M ]

  # Create instance: smartconnect_0, and set properties
  set smartconnect_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 smartconnect_0 ]

  # Create instance: sys_concat_intc, and set properties
  set sys_concat_intc [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 sys_concat_intc ]
  set_property -dict [ list \
   CONFIG.NUM_PORTS {16} \
 ] $sys_concat_intc

  # Create instance: sys_ps7, and set properties
  set sys_ps7 [ create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 sys_ps7 ]
  set_property -dict [ list \
   CONFIG.PCW_ACT_APU_PERIPHERAL_FREQMHZ {666.666687} \
   CONFIG.PCW_ACT_CAN_PERIPHERAL_FREQMHZ {10.000000} \
   CONFIG.PCW_ACT_DCI_PERIPHERAL_FREQMHZ {10.158730} \
   CONFIG.PCW_ACT_ENET0_PERIPHERAL_FREQMHZ {125.000000} \
   CONFIG.PCW_ACT_ENET1_PERIPHERAL_FREQMHZ {10.000000} \
   CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
   CONFIG.PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ {200.000000} \
   CONFIG.PCW_ACT_FPGA2_PERIPHERAL_FREQMHZ {250.000000} \
   CONFIG.PCW_ACT_FPGA3_PERIPHERAL_FREQMHZ {50.000000} \
   CONFIG.PCW_ACT_PCAP_PERIPHERAL_FREQMHZ {200.000000} \
   CONFIG.PCW_ACT_QSPI_PERIPHERAL_FREQMHZ {200.000000} \
   CONFIG.PCW_ACT_SDIO_PERIPHERAL_FREQMHZ {50.000000} \
   CONFIG.PCW_ACT_SMC_PERIPHERAL_FREQMHZ {10.000000} \
   CONFIG.PCW_ACT_SPI_PERIPHERAL_FREQMHZ {166.666672} \
   CONFIG.PCW_ACT_TPIU_PERIPHERAL_FREQMHZ {200.000000} \
   CONFIG.PCW_ACT_TTC0_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_TTC0_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_TTC0_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_TTC1_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_TTC1_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_TTC1_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ACT_UART_PERIPHERAL_FREQMHZ {100.000000} \
   CONFIG.PCW_ACT_WDT_PERIPHERAL_FREQMHZ {111.111115} \
   CONFIG.PCW_ARMPLL_CTRL_FBDIV {40} \
   CONFIG.PCW_CAN_PERIPHERAL_DIVISOR0 {1} \
   CONFIG.PCW_CAN_PERIPHERAL_DIVISOR1 {1} \
   CONFIG.PCW_CLK0_FREQ {100000000} \
   CONFIG.PCW_CLK1_FREQ {200000000} \
   CONFIG.PCW_CLK2_FREQ {250000000} \
   CONFIG.PCW_CLK3_FREQ {50000000} \
   CONFIG.PCW_CPU_CPU_PLL_FREQMHZ {1333.333} \
   CONFIG.PCW_CPU_PERIPHERAL_DIVISOR0 {2} \
   CONFIG.PCW_DCI_PERIPHERAL_DIVISOR0 {15} \
   CONFIG.PCW_DCI_PERIPHERAL_DIVISOR1 {7} \
   CONFIG.PCW_DDRPLL_CTRL_FBDIV {32} \
   CONFIG.PCW_DDR_DDR_PLL_FREQMHZ {1066.667} \
   CONFIG.PCW_DDR_PERIPHERAL_DIVISOR0 {2} \
   CONFIG.PCW_DDR_RAM_HIGHADDR {0x3FFFFFFF} \
   CONFIG.PCW_ENET0_ENET0_IO {MIO 16 .. 27} \
   CONFIG.PCW_ENET0_GRP_MDIO_ENABLE {1} \
   CONFIG.PCW_ENET0_GRP_MDIO_IO {MIO 52 .. 53} \
   CONFIG.PCW_ENET0_PERIPHERAL_CLKSRC {IO PLL} \
   CONFIG.PCW_ENET0_PERIPHERAL_DIVISOR0 {8} \
   CONFIG.PCW_ENET0_PERIPHERAL_DIVISOR1 {1} \
   CONFIG.PCW_ENET0_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_ENET0_PERIPHERAL_FREQMHZ {1000 Mbps} \
   CONFIG.PCW_ENET0_RESET_ENABLE {0} \
   CONFIG.PCW_ENET1_PERIPHERAL_DIVISOR0 {1} \
   CONFIG.PCW_ENET1_PERIPHERAL_DIVISOR1 {1} \
   CONFIG.PCW_ENET1_RESET_ENABLE {0} \
   CONFIG.PCW_ENET_RESET_ENABLE {1} \
   CONFIG.PCW_ENET_RESET_SELECT {Share reset pin} \
   CONFIG.PCW_EN_CLK1_PORT {1} \
   CONFIG.PCW_EN_CLK2_PORT {1} \
   CONFIG.PCW_EN_CLK3_PORT {1} \
   CONFIG.PCW_EN_EMIO_CD_SDIO1 {0} \
   CONFIG.PCW_EN_EMIO_ENET0 {0} \
   CONFIG.PCW_EN_EMIO_GPIO {1} \
   CONFIG.PCW_EN_EMIO_MODEM_UART1 {0} \
   CONFIG.PCW_EN_EMIO_SDIO1 {0} \
   CONFIG.PCW_EN_EMIO_SPI0 {1} \
   CONFIG.PCW_EN_EMIO_SPI1 {1} \
   CONFIG.PCW_EN_EMIO_TTC0 {1} \
   CONFIG.PCW_EN_EMIO_WP_SDIO1 {0} \
   CONFIG.PCW_EN_ENET0 {1} \
   CONFIG.PCW_EN_GPIO {1} \
   CONFIG.PCW_EN_MODEM_UART1 {0} \
   CONFIG.PCW_EN_QSPI {1} \
   CONFIG.PCW_EN_SDIO0 {1} \
   CONFIG.PCW_EN_SDIO1 {1} \
   CONFIG.PCW_EN_SPI0 {1} \
   CONFIG.PCW_EN_SPI1 {1} \
   CONFIG.PCW_EN_TTC0 {1} \
   CONFIG.PCW_EN_UART1 {1} \
   CONFIG.PCW_EN_USB0 {1} \
   CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR0 {5} \
   CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR1 {2} \
   CONFIG.PCW_FCLK1_PERIPHERAL_DIVISOR0 {5} \
   CONFIG.PCW_FCLK1_PERIPHERAL_DIVISOR1 {1} \
   CONFIG.PCW_FCLK2_PERIPHERAL_DIVISOR0 {2} \
   CONFIG.PCW_FCLK2_PERIPHERAL_DIVISOR1 {2} \
   CONFIG.PCW_FCLK3_PERIPHERAL_DIVISOR0 {5} \
   CONFIG.PCW_FCLK3_PERIPHERAL_DIVISOR1 {4} \
   CONFIG.PCW_FCLK_CLK1_BUF {TRUE} \
   CONFIG.PCW_FCLK_CLK2_BUF {TRUE} \
   CONFIG.PCW_FCLK_CLK3_BUF {TRUE} \
   CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
   CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {200} \
   CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ {250} \
   CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
   CONFIG.PCW_FPGA_FCLK1_ENABLE {1} \
   CONFIG.PCW_FPGA_FCLK2_ENABLE {1} \
   CONFIG.PCW_FPGA_FCLK3_ENABLE {1} \
   CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {1} \
   CONFIG.PCW_GPIO_EMIO_GPIO_IO {64} \
   CONFIG.PCW_GPIO_EMIO_GPIO_WIDTH {64} \
   CONFIG.PCW_GPIO_MIO_GPIO_ENABLE {1} \
   CONFIG.PCW_GPIO_MIO_GPIO_IO {MIO} \
   CONFIG.PCW_I2C0_RESET_ENABLE {0} \
   CONFIG.PCW_I2C1_RESET_ENABLE {0} \
   CONFIG.PCW_I2C_PERIPHERAL_FREQMHZ {25} \
   CONFIG.PCW_I2C_RESET_ENABLE {0} \
   CONFIG.PCW_IOPLL_CTRL_FBDIV {30} \
   CONFIG.PCW_IO_IO_PLL_FREQMHZ {1000.000} \
   CONFIG.PCW_IRQ_F2P_INTR {1} \
   CONFIG.PCW_IRQ_F2P_MODE {REVERSE} \
   CONFIG.PCW_MIO_0_DIRECTION {inout} \
   CONFIG.PCW_MIO_0_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_0_PULLUP {enabled} \
   CONFIG.PCW_MIO_0_SLEW {slow} \
   CONFIG.PCW_MIO_10_DIRECTION {inout} \
   CONFIG.PCW_MIO_10_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_10_PULLUP {enabled} \
   CONFIG.PCW_MIO_10_SLEW {slow} \
   CONFIG.PCW_MIO_11_DIRECTION {inout} \
   CONFIG.PCW_MIO_11_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_11_PULLUP {enabled} \
   CONFIG.PCW_MIO_11_SLEW {slow} \
   CONFIG.PCW_MIO_12_DIRECTION {out} \
   CONFIG.PCW_MIO_12_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_12_PULLUP {enabled} \
   CONFIG.PCW_MIO_12_SLEW {slow} \
   CONFIG.PCW_MIO_13_DIRECTION {in} \
   CONFIG.PCW_MIO_13_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_13_PULLUP {enabled} \
   CONFIG.PCW_MIO_13_SLEW {slow} \
   CONFIG.PCW_MIO_14_DIRECTION {inout} \
   CONFIG.PCW_MIO_14_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_14_PULLUP {enabled} \
   CONFIG.PCW_MIO_14_SLEW {slow} \
   CONFIG.PCW_MIO_15_DIRECTION {inout} \
   CONFIG.PCW_MIO_15_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_15_PULLUP {enabled} \
   CONFIG.PCW_MIO_15_SLEW {slow} \
   CONFIG.PCW_MIO_16_DIRECTION {out} \
   CONFIG.PCW_MIO_16_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_16_PULLUP {enabled} \
   CONFIG.PCW_MIO_16_SLEW {slow} \
   CONFIG.PCW_MIO_17_DIRECTION {out} \
   CONFIG.PCW_MIO_17_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_17_PULLUP {enabled} \
   CONFIG.PCW_MIO_17_SLEW {slow} \
   CONFIG.PCW_MIO_18_DIRECTION {out} \
   CONFIG.PCW_MIO_18_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_18_PULLUP {enabled} \
   CONFIG.PCW_MIO_18_SLEW {slow} \
   CONFIG.PCW_MIO_19_DIRECTION {out} \
   CONFIG.PCW_MIO_19_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_19_PULLUP {enabled} \
   CONFIG.PCW_MIO_19_SLEW {slow} \
   CONFIG.PCW_MIO_1_DIRECTION {out} \
   CONFIG.PCW_MIO_1_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_1_PULLUP {enabled} \
   CONFIG.PCW_MIO_1_SLEW {fast} \
   CONFIG.PCW_MIO_20_DIRECTION {out} \
   CONFIG.PCW_MIO_20_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_20_PULLUP {enabled} \
   CONFIG.PCW_MIO_20_SLEW {slow} \
   CONFIG.PCW_MIO_21_DIRECTION {out} \
   CONFIG.PCW_MIO_21_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_21_PULLUP {enabled} \
   CONFIG.PCW_MIO_21_SLEW {slow} \
   CONFIG.PCW_MIO_22_DIRECTION {in} \
   CONFIG.PCW_MIO_22_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_22_PULLUP {enabled} \
   CONFIG.PCW_MIO_22_SLEW {slow} \
   CONFIG.PCW_MIO_23_DIRECTION {in} \
   CONFIG.PCW_MIO_23_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_23_PULLUP {enabled} \
   CONFIG.PCW_MIO_23_SLEW {slow} \
   CONFIG.PCW_MIO_24_DIRECTION {in} \
   CONFIG.PCW_MIO_24_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_24_PULLUP {enabled} \
   CONFIG.PCW_MIO_24_SLEW {slow} \
   CONFIG.PCW_MIO_25_DIRECTION {in} \
   CONFIG.PCW_MIO_25_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_25_PULLUP {enabled} \
   CONFIG.PCW_MIO_25_SLEW {slow} \
   CONFIG.PCW_MIO_26_DIRECTION {in} \
   CONFIG.PCW_MIO_26_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_26_PULLUP {enabled} \
   CONFIG.PCW_MIO_26_SLEW {slow} \
   CONFIG.PCW_MIO_27_DIRECTION {in} \
   CONFIG.PCW_MIO_27_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_27_PULLUP {enabled} \
   CONFIG.PCW_MIO_27_SLEW {slow} \
   CONFIG.PCW_MIO_28_DIRECTION {inout} \
   CONFIG.PCW_MIO_28_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_28_PULLUP {enabled} \
   CONFIG.PCW_MIO_28_SLEW {slow} \
   CONFIG.PCW_MIO_29_DIRECTION {in} \
   CONFIG.PCW_MIO_29_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_29_PULLUP {enabled} \
   CONFIG.PCW_MIO_29_SLEW {slow} \
   CONFIG.PCW_MIO_2_DIRECTION {inout} \
   CONFIG.PCW_MIO_2_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_2_PULLUP {disabled} \
   CONFIG.PCW_MIO_2_SLEW {fast} \
   CONFIG.PCW_MIO_30_DIRECTION {out} \
   CONFIG.PCW_MIO_30_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_30_PULLUP {enabled} \
   CONFIG.PCW_MIO_30_SLEW {slow} \
   CONFIG.PCW_MIO_31_DIRECTION {in} \
   CONFIG.PCW_MIO_31_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_31_PULLUP {enabled} \
   CONFIG.PCW_MIO_31_SLEW {slow} \
   CONFIG.PCW_MIO_32_DIRECTION {inout} \
   CONFIG.PCW_MIO_32_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_32_PULLUP {enabled} \
   CONFIG.PCW_MIO_32_SLEW {slow} \
   CONFIG.PCW_MIO_33_DIRECTION {inout} \
   CONFIG.PCW_MIO_33_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_33_PULLUP {enabled} \
   CONFIG.PCW_MIO_33_SLEW {slow} \
   CONFIG.PCW_MIO_34_DIRECTION {inout} \
   CONFIG.PCW_MIO_34_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_34_PULLUP {enabled} \
   CONFIG.PCW_MIO_34_SLEW {slow} \
   CONFIG.PCW_MIO_35_DIRECTION {inout} \
   CONFIG.PCW_MIO_35_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_35_PULLUP {enabled} \
   CONFIG.PCW_MIO_35_SLEW {slow} \
   CONFIG.PCW_MIO_36_DIRECTION {in} \
   CONFIG.PCW_MIO_36_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_36_PULLUP {enabled} \
   CONFIG.PCW_MIO_36_SLEW {slow} \
   CONFIG.PCW_MIO_37_DIRECTION {inout} \
   CONFIG.PCW_MIO_37_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_37_PULLUP {enabled} \
   CONFIG.PCW_MIO_37_SLEW {slow} \
   CONFIG.PCW_MIO_38_DIRECTION {inout} \
   CONFIG.PCW_MIO_38_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_38_PULLUP {enabled} \
   CONFIG.PCW_MIO_38_SLEW {slow} \
   CONFIG.PCW_MIO_39_DIRECTION {inout} \
   CONFIG.PCW_MIO_39_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_39_PULLUP {enabled} \
   CONFIG.PCW_MIO_39_SLEW {slow} \
   CONFIG.PCW_MIO_3_DIRECTION {inout} \
   CONFIG.PCW_MIO_3_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_3_PULLUP {disabled} \
   CONFIG.PCW_MIO_3_SLEW {fast} \
   CONFIG.PCW_MIO_40_DIRECTION {inout} \
   CONFIG.PCW_MIO_40_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_40_PULLUP {enabled} \
   CONFIG.PCW_MIO_40_SLEW {fast} \
   CONFIG.PCW_MIO_41_DIRECTION {inout} \
   CONFIG.PCW_MIO_41_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_41_PULLUP {enabled} \
   CONFIG.PCW_MIO_41_SLEW {fast} \
   CONFIG.PCW_MIO_42_DIRECTION {inout} \
   CONFIG.PCW_MIO_42_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_42_PULLUP {enabled} \
   CONFIG.PCW_MIO_42_SLEW {fast} \
   CONFIG.PCW_MIO_43_DIRECTION {inout} \
   CONFIG.PCW_MIO_43_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_43_PULLUP {enabled} \
   CONFIG.PCW_MIO_43_SLEW {fast} \
   CONFIG.PCW_MIO_44_DIRECTION {inout} \
   CONFIG.PCW_MIO_44_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_44_PULLUP {enabled} \
   CONFIG.PCW_MIO_44_SLEW {fast} \
   CONFIG.PCW_MIO_45_DIRECTION {inout} \
   CONFIG.PCW_MIO_45_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_45_PULLUP {enabled} \
   CONFIG.PCW_MIO_45_SLEW {fast} \
   CONFIG.PCW_MIO_46_DIRECTION {inout} \
   CONFIG.PCW_MIO_46_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_46_PULLUP {enabled} \
   CONFIG.PCW_MIO_46_SLEW {slow} \
   CONFIG.PCW_MIO_47_DIRECTION {inout} \
   CONFIG.PCW_MIO_47_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_47_PULLUP {enabled} \
   CONFIG.PCW_MIO_47_SLEW {fast} \
   CONFIG.PCW_MIO_48_DIRECTION {inout} \
   CONFIG.PCW_MIO_48_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_48_PULLUP {enabled} \
   CONFIG.PCW_MIO_48_SLEW {fast} \
   CONFIG.PCW_MIO_49_DIRECTION {inout} \
   CONFIG.PCW_MIO_49_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_49_PULLUP {enabled} \
   CONFIG.PCW_MIO_49_SLEW {fast} \
   CONFIG.PCW_MIO_4_DIRECTION {inout} \
   CONFIG.PCW_MIO_4_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_4_PULLUP {disabled} \
   CONFIG.PCW_MIO_4_SLEW {fast} \
   CONFIG.PCW_MIO_50_DIRECTION {inout} \
   CONFIG.PCW_MIO_50_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_50_PULLUP {enabled} \
   CONFIG.PCW_MIO_50_SLEW {fast} \
   CONFIG.PCW_MIO_51_DIRECTION {inout} \
   CONFIG.PCW_MIO_51_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_51_PULLUP {enabled} \
   CONFIG.PCW_MIO_51_SLEW {fast} \
   CONFIG.PCW_MIO_52_DIRECTION {out} \
   CONFIG.PCW_MIO_52_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_52_PULLUP {enabled} \
   CONFIG.PCW_MIO_52_SLEW {slow} \
   CONFIG.PCW_MIO_53_DIRECTION {inout} \
   CONFIG.PCW_MIO_53_IOTYPE {LVCMOS 1.8V} \
   CONFIG.PCW_MIO_53_PULLUP {enabled} \
   CONFIG.PCW_MIO_53_SLEW {slow} \
   CONFIG.PCW_MIO_5_DIRECTION {inout} \
   CONFIG.PCW_MIO_5_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_5_PULLUP {disabled} \
   CONFIG.PCW_MIO_5_SLEW {fast} \
   CONFIG.PCW_MIO_6_DIRECTION {out} \
   CONFIG.PCW_MIO_6_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_6_PULLUP {disabled} \
   CONFIG.PCW_MIO_6_SLEW {fast} \
   CONFIG.PCW_MIO_7_DIRECTION {out} \
   CONFIG.PCW_MIO_7_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_7_PULLUP {disabled} \
   CONFIG.PCW_MIO_7_SLEW {slow} \
   CONFIG.PCW_MIO_8_DIRECTION {out} \
   CONFIG.PCW_MIO_8_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_8_PULLUP {disabled} \
   CONFIG.PCW_MIO_8_SLEW {slow} \
   CONFIG.PCW_MIO_9_DIRECTION {inout} \
   CONFIG.PCW_MIO_9_IOTYPE {LVCMOS 3.3V} \
   CONFIG.PCW_MIO_9_PULLUP {enabled} \
   CONFIG.PCW_MIO_9_SLEW {slow} \
   CONFIG.PCW_MIO_TREE_PERIPHERALS {GPIO#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI Flash#Quad SPI\
Flash#Quad SPI Flash#GPIO#GPIO#GPIO#GPIO#GPIO#UART 1#UART 1#GPIO#GPIO#Enet\
0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet 0#Enet\
0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#USB 0#SD\
0#SD 0#SD 0#SD 0#SD 0#SD 0#SD 1#SD 1#SD 1#SD 1#SD 1#SD 1#Enet 0#Enet 0}\
   CONFIG.PCW_MIO_TREE_SIGNALS {gpio[0]#qspi0_ss_b#qspi0_io[0]#qspi0_io[1]#qspi0_io[2]#qspi0_io[3]/HOLD_B#qspi0_sclk#gpio[7]#gpio[8]#gpio[9]#gpio[10]#gpio[11]#tx#rx#gpio[14]#gpio[15]#tx_clk#txd[0]#txd[1]#txd[2]#txd[3]#tx_ctl#rx_clk#rxd[0]#rxd[1]#rxd[2]#rxd[3]#rx_ctl#data[4]#dir#stp#nxt#data[0]#data[1]#data[2]#data[3]#clk#data[5]#data[6]#data[7]#clk#cmd#data[0]#data[1]#data[2]#data[3]#data[0]#cmd#clk#data[1]#data[2]#data[3]#mdc#mdio}\
   CONFIG.PCW_NAND_GRP_D8_ENABLE {0} \
   CONFIG.PCW_NAND_PERIPHERAL_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_A25_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_CS0_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_CS1_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_SRAM_CS0_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_SRAM_CS1_ENABLE {0} \
   CONFIG.PCW_NOR_GRP_SRAM_INT_ENABLE {0} \
   CONFIG.PCW_NOR_PERIPHERAL_ENABLE {0} \
   CONFIG.PCW_PCAP_PERIPHERAL_DIVISOR0 {5} \
   CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V} \
   CONFIG.PCW_QSPI_GRP_FBCLK_ENABLE {0} \
   CONFIG.PCW_QSPI_GRP_IO1_ENABLE {0} \
   CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE {1} \
   CONFIG.PCW_QSPI_GRP_SINGLE_SS_IO {MIO 1 .. 6} \
   CONFIG.PCW_QSPI_GRP_SS1_ENABLE {0} \
   CONFIG.PCW_QSPI_PERIPHERAL_DIVISOR0 {5} \
   CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_QSPI_PERIPHERAL_FREQMHZ {200} \
   CONFIG.PCW_QSPI_QSPI_IO {MIO 1 .. 6} \
   CONFIG.PCW_SD0_GRP_CD_ENABLE {0} \
   CONFIG.PCW_SD0_GRP_POW_ENABLE {0} \
   CONFIG.PCW_SD0_GRP_WP_ENABLE {0} \
   CONFIG.PCW_SD0_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_SD0_SD0_IO {MIO 40 .. 45} \
   CONFIG.PCW_SD1_GRP_CD_ENABLE {0} \
   CONFIG.PCW_SD1_GRP_POW_ENABLE {0} \
   CONFIG.PCW_SD1_GRP_WP_ENABLE {0} \
   CONFIG.PCW_SD1_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_SD1_SD1_IO {MIO 46 .. 51} \
   CONFIG.PCW_SDIO_PERIPHERAL_DIVISOR0 {20} \
   CONFIG.PCW_SDIO_PERIPHERAL_FREQMHZ {50} \
   CONFIG.PCW_SDIO_PERIPHERAL_VALID {1} \
   CONFIG.PCW_SINGLE_QSPI_DATA_MODE {x4} \
   CONFIG.PCW_SMC_PERIPHERAL_DIVISOR0 {1} \
   CONFIG.PCW_SPI0_GRP_SS0_ENABLE {1} \
   CONFIG.PCW_SPI0_GRP_SS0_IO {EMIO} \
   CONFIG.PCW_SPI0_GRP_SS1_ENABLE {1} \
   CONFIG.PCW_SPI0_GRP_SS1_IO {EMIO} \
   CONFIG.PCW_SPI0_GRP_SS2_ENABLE {1} \
   CONFIG.PCW_SPI0_GRP_SS2_IO {EMIO} \
   CONFIG.PCW_SPI0_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_SPI0_SPI0_IO {EMIO} \
   CONFIG.PCW_SPI1_GRP_SS0_ENABLE {1} \
   CONFIG.PCW_SPI1_GRP_SS0_IO {EMIO} \
   CONFIG.PCW_SPI1_GRP_SS1_ENABLE {1} \
   CONFIG.PCW_SPI1_GRP_SS1_IO {EMIO} \
   CONFIG.PCW_SPI1_GRP_SS2_ENABLE {1} \
   CONFIG.PCW_SPI1_GRP_SS2_IO {EMIO} \
   CONFIG.PCW_SPI1_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_SPI1_SPI1_IO {EMIO} \
   CONFIG.PCW_SPI_PERIPHERAL_DIVISOR0 {6} \
   CONFIG.PCW_SPI_PERIPHERAL_FREQMHZ {166.666666} \
   CONFIG.PCW_SPI_PERIPHERAL_VALID {1} \
   CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
   CONFIG.PCW_TPIU_PERIPHERAL_DIVISOR0 {1} \
   CONFIG.PCW_TTC0_CLK0_PERIPHERAL_FREQMHZ {133.333333} \
   CONFIG.PCW_TTC0_CLK1_PERIPHERAL_FREQMHZ {133.333333} \
   CONFIG.PCW_TTC0_CLK2_PERIPHERAL_FREQMHZ {133.333333} \
   CONFIG.PCW_TTC0_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_TTC0_TTC0_IO {EMIO} \
   CONFIG.PCW_TTC_PERIPHERAL_FREQMHZ {50} \
   CONFIG.PCW_UART1_GRP_FULL_ENABLE {0} \
   CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_UART1_UART1_IO {MIO 12 .. 13} \
   CONFIG.PCW_UART_PERIPHERAL_DIVISOR0 {10} \
   CONFIG.PCW_UART_PERIPHERAL_FREQMHZ {100} \
   CONFIG.PCW_UART_PERIPHERAL_VALID {1} \
   CONFIG.PCW_UIPARAM_ACT_DDR_FREQ_MHZ {533.333374} \
   CONFIG.PCW_UIPARAM_DDR_BANK_ADDR_COUNT {3} \
   CONFIG.PCW_UIPARAM_DDR_CL {7} \
   CONFIG.PCW_UIPARAM_DDR_COL_ADDR_COUNT {10} \
   CONFIG.PCW_UIPARAM_DDR_CWL {6} \
   CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY {4096 MBits} \
   CONFIG.PCW_UIPARAM_DDR_DRAM_WIDTH {16 Bits} \
   CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
   CONFIG.PCW_UIPARAM_DDR_ROW_ADDR_COUNT {15} \
   CONFIG.PCW_UIPARAM_DDR_SPEED_BIN {DDR3_1066F} \
   CONFIG.PCW_UIPARAM_DDR_T_FAW {40.0} \
   CONFIG.PCW_UIPARAM_DDR_T_RAS_MIN {35.0} \
   CONFIG.PCW_UIPARAM_DDR_T_RC {48.75} \
   CONFIG.PCW_UIPARAM_DDR_T_RCD {7} \
   CONFIG.PCW_UIPARAM_DDR_T_RP {7} \
   CONFIG.PCW_USB0_PERIPHERAL_ENABLE {1} \
   CONFIG.PCW_USB0_PERIPHERAL_FREQMHZ {60} \
   CONFIG.PCW_USB0_RESET_ENABLE {0} \
   CONFIG.PCW_USB0_USB0_IO {MIO 28 .. 39} \
   CONFIG.PCW_USB1_RESET_ENABLE {0} \
   CONFIG.PCW_USB_RESET_ENABLE {0} \
   CONFIG.PCW_USE_DMA0 {1} \
   CONFIG.PCW_USE_FABRIC_INTERRUPT {1} \
   CONFIG.PCW_USE_S_AXI_HP0 {1} \
   CONFIG.PCW_USE_S_AXI_HP1 {1} \
   CONFIG.PCW_USE_S_AXI_HP2 {1} \
 ] $sys_ps7

  # Create instance: sys_rstgen, and set properties
  set sys_rstgen [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 sys_rstgen ]
  set_property -dict [ list \
   CONFIG.C_EXT_RST_WIDTH {1} \
 ] $sys_rstgen

  # Create instance: util_ad9361_adc_fifo, and set properties
  set util_ad9361_adc_fifo [ create_bd_cell -type ip -vlnv analog.com:user:util_wfifo:1.0 util_ad9361_adc_fifo ]
  set_property -dict [ list \
   CONFIG.DIN_ADDRESS_WIDTH {4} \
   CONFIG.DIN_DATA_WIDTH {16} \
   CONFIG.DOUT_DATA_WIDTH {16} \
   CONFIG.NUM_OF_CHANNELS {4} \
 ] $util_ad9361_adc_fifo

  # Create instance: util_ad9361_adc_pack, and set properties
  set util_ad9361_adc_pack [ create_bd_cell -type ip -vlnv analog.com:user:util_cpack:1.0 util_ad9361_adc_pack ]
  set_property -dict [ list \
   CONFIG.CHANNEL_DATA_WIDTH {16} \
   CONFIG.NUM_OF_CHANNELS {4} \
 ] $util_ad9361_adc_pack

  # Create instance: util_ad9361_dac_upack, and set properties
  set util_ad9361_dac_upack [ create_bd_cell -type ip -vlnv analog.com:user:util_upack:1.0 util_ad9361_dac_upack ]
  set_property -dict [ list \
   CONFIG.CHANNEL_DATA_WIDTH {16} \
   CONFIG.NUM_OF_CHANNELS {4} \
 ] $util_ad9361_dac_upack

  # Create instance: util_ad9361_divclk, and set properties
  set util_ad9361_divclk [ create_bd_cell -type ip -vlnv analog.com:user:util_clkdiv:1.0 util_ad9361_divclk ]

  # Create instance: util_ad9361_divclk_reset, and set properties
  set util_ad9361_divclk_reset [ create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 util_ad9361_divclk_reset ]

  # Create instance: util_ad9361_divclk_sel, and set properties
  set util_ad9361_divclk_sel [ create_bd_cell -type ip -vlnv xilinx.com:ip:util_reduced_logic:2.0 util_ad9361_divclk_sel ]
  set_property -dict [ list \
   CONFIG.C_SIZE {2} \
 ] $util_ad9361_divclk_sel

  # Create instance: util_ad9361_divclk_sel_concat, and set properties
  set util_ad9361_divclk_sel_concat [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 util_ad9361_divclk_sel_concat ]
  set_property -dict [ list \
   CONFIG.NUM_PORTS {2} \
 ] $util_ad9361_divclk_sel_concat

  # Create instance: util_ad9361_tdd_sync, and set properties
  set util_ad9361_tdd_sync [ create_bd_cell -type ip -vlnv analog.com:user:util_tdd_sync:1.0 util_ad9361_tdd_sync ]
  set_property -dict [ list \
   CONFIG.TDD_SYNC_PERIOD {10000000} \
 ] $util_ad9361_tdd_sync

  # Create instance: v_axi4s_vid_out_0, and set properties
  set v_axi4s_vid_out_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_axi4s_vid_out:4.0 v_axi4s_vid_out_0 ]
  set_property -dict [ list \
   CONFIG.C_ADDR_WIDTH {12} \
   CONFIG.C_HAS_ASYNC_CLK {1} \
   CONFIG.C_NATIVE_COMPONENT_WIDTH {8} \
   CONFIG.C_VTG_MASTER_SLAVE {0} \
 ] $v_axi4s_vid_out_0

  # Create instance: v_tc_0, and set properties
  set v_tc_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 v_tc_0 ]
  set_property -dict [ list \
   CONFIG.GEN_F0_VBLANK_HEND {960} \
   CONFIG.GEN_F0_VBLANK_HSTART {960} \
   CONFIG.GEN_F0_VFRAME_SIZE {1125} \
   CONFIG.GEN_F0_VSYNC_HEND {1004} \
   CONFIG.GEN_F0_VSYNC_HSTART {1004} \
   CONFIG.GEN_F0_VSYNC_VEND {1088} \
   CONFIG.GEN_F0_VSYNC_VSTART {1083} \
   CONFIG.GEN_F1_VBLANK_HEND {960} \
   CONFIG.GEN_F1_VBLANK_HSTART {960} \
   CONFIG.GEN_F1_VFRAME_SIZE {1125} \
   CONFIG.GEN_F1_VSYNC_HEND {1004} \
   CONFIG.GEN_F1_VSYNC_HSTART {1004} \
   CONFIG.GEN_F1_VSYNC_VEND {1088} \
   CONFIG.GEN_F1_VSYNC_VSTART {1083} \
   CONFIG.GEN_HACTIVE_SIZE {1920} \
   CONFIG.GEN_HFRAME_SIZE {2200} \
   CONFIG.GEN_HSYNC_END {2052} \
   CONFIG.GEN_HSYNC_START {2008} \
   CONFIG.GEN_VACTIVE_SIZE {1080} \
   CONFIG.HAS_AXI4_LITE {true} \
   CONFIG.VIDEO_MODE {1080p} \
   CONFIG.enable_detection {false} \
 ] $v_tc_0

  # Create instance: v_tpg_0, and set properties
  set v_tpg_0 [ create_bd_cell -type ip -vlnv xilinx.com:ip:v_tpg:8.1 v_tpg_0 ]
  set_property -dict [ list \
   CONFIG.MAX_DATA_WIDTH {8} \
   CONFIG.MAX_ROWS {4096} \
 ] $v_tpg_0

  # Create instance: xlslice_B, and set properties
  set xlslice_B [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 xlslice_B ]
  set_property -dict [ list \
   CONFIG.DIN_FROM {7} \
   CONFIG.DIN_TO {3} \
   CONFIG.DIN_WIDTH {24} \
   CONFIG.DOUT_WIDTH {5} \
 ] $xlslice_B

  # Create instance: xlslice_G, and set properties
  set xlslice_G [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 xlslice_G ]
  set_property -dict [ list \
   CONFIG.DIN_FROM {15} \
   CONFIG.DIN_TO {10} \
   CONFIG.DIN_WIDTH {24} \
   CONFIG.DOUT_WIDTH {6} \
 ] $xlslice_G

  # Create instance: xlslice_R, and set properties
  set xlslice_R [ create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 xlslice_R ]
  set_property -dict [ list \
   CONFIG.DIN_FROM {23} \
   CONFIG.DIN_TO {19} \
   CONFIG.DIN_WIDTH {24} \
   CONFIG.DOUT_WIDTH {5} \
 ] $xlslice_R

  # Create interface connections
  connect_bd_intf_net -intf_net S00_AXI_1 [get_bd_intf_pins axi_cpu_interconnect/S00_AXI] [get_bd_intf_pins sys_ps7/M_AXI_GP0]
  connect_bd_intf_net -intf_net S00_AXI_3 [get_bd_intf_pins axi_ad9361_adc_dma/m_dest_axi] [get_bd_intf_pins axi_hp1_interconnect/S00_AXI]
  connect_bd_intf_net -intf_net S00_AXI_4 [get_bd_intf_pins axi_ad9361_dac_dma/m_src_axi] [get_bd_intf_pins axi_hp2_interconnect/S00_AXI]
  connect_bd_intf_net -intf_net axi_cpu_interconnect_M05_AXI [get_bd_intf_pins axi_ad9361/s_axi] [get_bd_intf_pins axi_cpu_interconnect/M05_AXI]
  connect_bd_intf_net -intf_net axi_cpu_interconnect_M06_AXI [get_bd_intf_pins axi_ad9361_adc_dma/s_axi] [get_bd_intf_pins axi_cpu_interconnect/M06_AXI]
  connect_bd_intf_net -intf_net axi_cpu_interconnect_M07_AXI [get_bd_intf_pins axi_ad9361_dac_dma/s_axi] [get_bd_intf_pins axi_cpu_interconnect/M07_AXI]
  connect_bd_intf_net -intf_net axi_hp1_interconnect_M00_AXI [get_bd_intf_pins axi_hp1_interconnect/M00_AXI] [get_bd_intf_pins sys_ps7/S_AXI_HP1]
  connect_bd_intf_net -intf_net axi_hp2_interconnect_M00_AXI [get_bd_intf_pins axi_hp2_interconnect/M00_AXI] [get_bd_intf_pins sys_ps7/S_AXI_HP2]
  connect_bd_intf_net -intf_net display_axi_vdma_0_M_AXIS_MM2S [get_bd_intf_pins axi_vdma_0/M_AXIS_MM2S] [get_bd_intf_pins axis_subset_converter_1/S_AXIS]
  connect_bd_intf_net -intf_net display_axi_vdma_0_M_AXI_MM2S [get_bd_intf_pins axi_vdma_0/M_AXI_MM2S] [get_bd_intf_pins smartconnect_0/S00_AXI]
  connect_bd_intf_net -intf_net display_axi_vdma_0_M_AXI_S2MM [get_bd_intf_pins axi_vdma_0/M_AXI_S2MM] [get_bd_intf_pins smartconnect_0/S01_AXI]
  connect_bd_intf_net -intf_net display_axis_subset_converter_0_M_AXIS [get_bd_intf_pins axi_vdma_0/S_AXIS_S2MM] [get_bd_intf_pins axis_subset_converter_0/M_AXIS]
  connect_bd_intf_net -intf_net display_axis_subset_converter_1_M_AXIS [get_bd_intf_pins axis_subset_converter_1/M_AXIS] [get_bd_intf_pins v_axi4s_vid_out_0/video_in]
  connect_bd_intf_net -intf_net display_ps7_0_axi_periph_M00_AXI [get_bd_intf_pins axi_cpu_interconnect/M00_AXI] [get_bd_intf_pins v_tpg_0/s_axi_CTRL]
  connect_bd_intf_net -intf_net display_ps7_0_axi_periph_M01_AXI [get_bd_intf_pins axi_cpu_interconnect/M01_AXI] [get_bd_intf_pins clk_wiz_0/s_axi_lite]
  connect_bd_intf_net -intf_net display_ps7_0_axi_periph_M02_AXI [get_bd_intf_pins axi_cpu_interconnect/M02_AXI] [get_bd_intf_pins v_tc_0/ctrl]
  connect_bd_intf_net -intf_net display_ps7_0_axi_periph_M03_AXI [get_bd_intf_pins axi_cpu_interconnect/M03_AXI] [get_bd_intf_pins axi_vdma_0/S_AXI_LITE]
  connect_bd_intf_net -intf_net display_smartconnect_0_M00_AXI [get_bd_intf_pins smartconnect_0/M00_AXI] [get_bd_intf_pins sys_ps7/S_AXI_HP0]
  connect_bd_intf_net -intf_net display_v_tc_0_vtiming_out [get_bd_intf_pins v_axi4s_vid_out_0/vtiming_in] [get_bd_intf_pins v_tc_0/vtiming_out]
  connect_bd_intf_net -intf_net display_v_tpg_0_m_axis_video [get_bd_intf_pins axis_subset_converter_0/S_AXIS] [get_bd_intf_pins v_tpg_0/m_axis_video]
  connect_bd_intf_net -intf_net sys_ps7_DDR [get_bd_intf_ports ddr] [get_bd_intf_pins sys_ps7/DDR]
  connect_bd_intf_net -intf_net sys_ps7_FIXED_IO [get_bd_intf_ports fixed_io] [get_bd_intf_pins sys_ps7/FIXED_IO]

  # Create port connections
  connect_bd_net -net GPIO_I_0_1 [get_bd_ports gpio_i] [get_bd_pins sys_ps7/GPIO_I]
  connect_bd_net -net axi_ad9361_adc_data_i0 [get_bd_pins axi_ad9361/adc_data_i0] [get_bd_pins util_ad9361_adc_fifo/din_data_0]
  connect_bd_net -net axi_ad9361_adc_data_i1 [get_bd_pins axi_ad9361/adc_data_i1] [get_bd_pins util_ad9361_adc_fifo/din_data_2]
  connect_bd_net -net axi_ad9361_adc_data_q0 [get_bd_pins axi_ad9361/adc_data_q0] [get_bd_pins util_ad9361_adc_fifo/din_data_1]
  connect_bd_net -net axi_ad9361_adc_data_q1 [get_bd_pins axi_ad9361/adc_data_q1] [get_bd_pins util_ad9361_adc_fifo/din_data_3]
  connect_bd_net -net axi_ad9361_adc_dma_fifo_wr_overflow [get_bd_pins axi_ad9361_adc_dma/fifo_wr_overflow] [get_bd_pins util_ad9361_adc_fifo/dout_ovf]
  connect_bd_net -net axi_ad9361_adc_dma_irq [get_bd_pins axi_ad9361_adc_dma/irq] [get_bd_pins sys_concat_intc/In13]
  connect_bd_net -net axi_ad9361_adc_enable_i0 [get_bd_pins axi_ad9361/adc_enable_i0] [get_bd_pins util_ad9361_adc_fifo/din_enable_0]
  connect_bd_net -net axi_ad9361_adc_enable_i1 [get_bd_pins axi_ad9361/adc_enable_i1] [get_bd_pins util_ad9361_adc_fifo/din_enable_2]
  connect_bd_net -net axi_ad9361_adc_enable_q0 [get_bd_pins axi_ad9361/adc_enable_q0] [get_bd_pins util_ad9361_adc_fifo/din_enable_1]
  connect_bd_net -net axi_ad9361_adc_enable_q1 [get_bd_pins axi_ad9361/adc_enable_q1] [get_bd_pins util_ad9361_adc_fifo/din_enable_3]
  connect_bd_net -net axi_ad9361_adc_r1_mode [get_bd_pins axi_ad9361/adc_r1_mode] [get_bd_pins util_ad9361_divclk_sel_concat/In0]
  connect_bd_net -net axi_ad9361_adc_valid_i0 [get_bd_pins axi_ad9361/adc_valid_i0] [get_bd_pins util_ad9361_adc_fifo/din_valid_0]
  connect_bd_net -net axi_ad9361_adc_valid_i1 [get_bd_pins axi_ad9361/adc_valid_i1] [get_bd_pins util_ad9361_adc_fifo/din_valid_2]
  connect_bd_net -net axi_ad9361_adc_valid_q0 [get_bd_pins axi_ad9361/adc_valid_q0] [get_bd_pins util_ad9361_adc_fifo/din_valid_1]
  connect_bd_net -net axi_ad9361_adc_valid_q1 [get_bd_pins axi_ad9361/adc_valid_q1] [get_bd_pins util_ad9361_adc_fifo/din_valid_3]
  connect_bd_net -net axi_ad9361_dac_dma_fifo_rd_dout [get_bd_pins axi_ad9361_dac_dma/fifo_rd_dout] [get_bd_pins util_ad9361_dac_upack/dac_data]
  connect_bd_net -net axi_ad9361_dac_dma_fifo_rd_underflow [get_bd_pins axi_ad9361_dac_dma/fifo_rd_underflow] [get_bd_pins axi_ad9361_dac_fifo/din_unf]
  connect_bd_net -net axi_ad9361_dac_dma_irq [get_bd_pins axi_ad9361_dac_dma/irq] [get_bd_pins sys_concat_intc/In12]
  connect_bd_net -net axi_ad9361_dac_enable_i0 [get_bd_pins axi_ad9361/dac_enable_i0] [get_bd_pins axi_ad9361_dac_fifo/dout_enable_0]
  connect_bd_net -net axi_ad9361_dac_enable_i1 [get_bd_pins axi_ad9361/dac_enable_i1] [get_bd_pins axi_ad9361_dac_fifo/dout_enable_2]
  connect_bd_net -net axi_ad9361_dac_enable_q0 [get_bd_pins axi_ad9361/dac_enable_q0] [get_bd_pins axi_ad9361_dac_fifo/dout_enable_1]
  connect_bd_net -net axi_ad9361_dac_enable_q1 [get_bd_pins axi_ad9361/dac_enable_q1] [get_bd_pins axi_ad9361_dac_fifo/dout_enable_3]
  connect_bd_net -net axi_ad9361_dac_fifo_din_enable_0 [get_bd_pins axi_ad9361_dac_fifo/din_enable_0] [get_bd_pins util_ad9361_dac_upack/dac_enable_0]
  connect_bd_net -net axi_ad9361_dac_fifo_din_enable_1 [get_bd_pins axi_ad9361_dac_fifo/din_enable_1] [get_bd_pins util_ad9361_dac_upack/dac_enable_1]
  connect_bd_net -net axi_ad9361_dac_fifo_din_enable_2 [get_bd_pins axi_ad9361_dac_fifo/din_enable_2] [get_bd_pins util_ad9361_dac_upack/dac_enable_2]
  connect_bd_net -net axi_ad9361_dac_fifo_din_enable_3 [get_bd_pins axi_ad9361_dac_fifo/din_enable_3] [get_bd_pins util_ad9361_dac_upack/dac_enable_3]
  connect_bd_net -net axi_ad9361_dac_fifo_din_valid_0 [get_bd_pins axi_ad9361_dac_fifo/din_valid_0] [get_bd_pins util_ad9361_dac_upack/dac_valid_0]
  connect_bd_net -net axi_ad9361_dac_fifo_din_valid_1 [get_bd_pins axi_ad9361_dac_fifo/din_valid_1] [get_bd_pins util_ad9361_dac_upack/dac_valid_1]
  connect_bd_net -net axi_ad9361_dac_fifo_din_valid_2 [get_bd_pins axi_ad9361_dac_fifo/din_valid_2] [get_bd_pins util_ad9361_dac_upack/dac_valid_2]
  connect_bd_net -net axi_ad9361_dac_fifo_din_valid_3 [get_bd_pins axi_ad9361_dac_fifo/din_valid_3] [get_bd_pins util_ad9361_dac_upack/dac_valid_3]
  connect_bd_net -net axi_ad9361_dac_fifo_dout_data_0 [get_bd_pins axi_ad9361/dac_data_i0] [get_bd_pins axi_ad9361_dac_fifo/dout_data_0]
  connect_bd_net -net axi_ad9361_dac_fifo_dout_data_1 [get_bd_pins axi_ad9361/dac_data_q0] [get_bd_pins axi_ad9361_dac_fifo/dout_data_1]
  connect_bd_net -net axi_ad9361_dac_fifo_dout_data_2 [get_bd_pins axi_ad9361/dac_data_i1] [get_bd_pins axi_ad9361_dac_fifo/dout_data_2]
  connect_bd_net -net axi_ad9361_dac_fifo_dout_data_3 [get_bd_pins axi_ad9361/dac_data_q1] [get_bd_pins axi_ad9361_dac_fifo/dout_data_3]
  connect_bd_net -net axi_ad9361_dac_fifo_dout_unf [get_bd_pins axi_ad9361/dac_dunf] [get_bd_pins axi_ad9361_dac_fifo/dout_unf]
  connect_bd_net -net axi_ad9361_dac_r1_mode [get_bd_pins axi_ad9361/dac_r1_mode] [get_bd_pins util_ad9361_divclk_sel_concat/In1]
  connect_bd_net -net axi_ad9361_dac_valid_i0 [get_bd_pins axi_ad9361/dac_valid_i0] [get_bd_pins axi_ad9361_dac_fifo/dout_valid_0]
  connect_bd_net -net axi_ad9361_dac_valid_i1 [get_bd_pins axi_ad9361/dac_valid_i1] [get_bd_pins axi_ad9361_dac_fifo/dout_valid_2]
  connect_bd_net -net axi_ad9361_dac_valid_q0 [get_bd_pins axi_ad9361/dac_valid_q0] [get_bd_pins axi_ad9361_dac_fifo/dout_valid_1]
  connect_bd_net -net axi_ad9361_dac_valid_q1 [get_bd_pins axi_ad9361/dac_valid_q1] [get_bd_pins axi_ad9361_dac_fifo/dout_valid_3]
  connect_bd_net -net axi_ad9361_enable [get_bd_ports enable] [get_bd_pins axi_ad9361/enable]
  connect_bd_net -net axi_ad9361_l_clk [get_bd_pins axi_ad9361/clk] [get_bd_pins axi_ad9361/l_clk] [get_bd_pins axi_ad9361_dac_fifo/dout_clk] [get_bd_pins util_ad9361_adc_fifo/din_clk] [get_bd_pins util_ad9361_divclk/clk]
  connect_bd_net -net axi_ad9361_rst [get_bd_pins axi_ad9361/rst] [get_bd_pins axi_ad9361_dac_fifo/dout_rst] [get_bd_pins util_ad9361_adc_fifo/din_rst]
  connect_bd_net -net axi_ad9361_tdd_sync_cntr [get_bd_ports tdd_sync_t] [get_bd_pins axi_ad9361/tdd_sync_cntr] [get_bd_pins util_ad9361_tdd_sync/sync_mode]
  connect_bd_net -net axi_ad9361_tx_clk_out_n [get_bd_ports tx_clk_out_n] [get_bd_pins axi_ad9361/tx_clk_out_n]
  connect_bd_net -net axi_ad9361_tx_clk_out_p [get_bd_ports tx_clk_out_p] [get_bd_pins axi_ad9361/tx_clk_out_p]
  connect_bd_net -net axi_ad9361_tx_data_out_n [get_bd_ports tx_data_out_n] [get_bd_pins axi_ad9361/tx_data_out_n]
  connect_bd_net -net axi_ad9361_tx_data_out_p [get_bd_ports tx_data_out_p] [get_bd_pins axi_ad9361/tx_data_out_p]
  connect_bd_net -net axi_ad9361_tx_frame_out_n [get_bd_ports tx_frame_out_n] [get_bd_pins axi_ad9361/tx_frame_out_n]
  connect_bd_net -net axi_ad9361_tx_frame_out_p [get_bd_ports tx_frame_out_p] [get_bd_pins axi_ad9361/tx_frame_out_p]
  connect_bd_net -net axi_ad9361_txnrx [get_bd_ports txnrx] [get_bd_pins axi_ad9361/txnrx]
  connect_bd_net -net display_SPI0_MISO_I_0_1 [get_bd_ports SPI0_MISO_I] [get_bd_pins sys_ps7/SPI0_MISO_I]
  connect_bd_net -net display_axi_vdma_0_mm2s_introut [get_bd_pins axi_vdma_0/mm2s_introut] [get_bd_pins sys_concat_intc/In0]
  connect_bd_net -net display_axi_vdma_0_s2mm_introut [get_bd_pins axi_vdma_0/s2mm_introut] [get_bd_pins sys_concat_intc/In1]
  connect_bd_net -net display_clk_wiz_0_clk_out1 [get_bd_ports lcd_pclk] [get_bd_ports o_video_pclk] [get_bd_pins clk_wiz_0/clk_out1] [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/pclk_in] [get_bd_pins rst_clk_wiz_out/slowest_sync_clk] [get_bd_pins v_axi4s_vid_out_0/vid_io_out_clk] [get_bd_pins v_tc_0/clk]
  connect_bd_net -net display_clk_wiz_0_locked [get_bd_pins clk_wiz_0/locked] [get_bd_pins rst_clk_wiz_out/dcm_locked] [get_bd_pins v_axi4s_vid_out_0/aclken] [get_bd_pins v_tc_0/clken] [get_bd_pins v_tc_0/resetn]
  connect_bd_net -net display_dual_pixel_24bpp_lvds_mapping_0_data_out [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/data_out] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/data_in]
  connect_bd_net -net display_dual_pixel_24bpp_lvds_mapping_0_pclk_out [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/pclk_out] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/clk_in]
  connect_bd_net -net display_lvds_n_x_7to1_sdr_tx_0_clk_out_n [get_bd_ports lvds_clk_out_n] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/clk_out_n]
  connect_bd_net -net display_lvds_n_x_7to1_sdr_tx_0_clk_out_p [get_bd_ports lvds_clk_out_p] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/clk_out_p]
  connect_bd_net -net display_lvds_n_x_7to1_sdr_tx_0_data_out_n [get_bd_ports lvds_data_out_n] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/data_out_n]
  connect_bd_net -net display_lvds_n_x_7to1_sdr_tx_0_data_out_p [get_bd_ports lvds_data_out_p] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/data_out_p]
  connect_bd_net -net display_processing_system7_0_SPI0_MOSI_O [get_bd_ports SPI0_MOSI_O] [get_bd_pins sys_ps7/SPI0_MOSI_O]
  connect_bd_net -net display_processing_system7_0_SPI0_SCLK_O [get_bd_ports SPI0_SCLK_O] [get_bd_pins sys_ps7/SPI0_SCLK_O]
  connect_bd_net -net display_processing_system7_0_SPI0_SS_O [get_bd_ports SPI0_SS_O] [get_bd_pins sys_ps7/SPI0_SS_O]
  connect_bd_net -net display_processing_system7_0_TTC0_WAVE0_OUT [get_bd_ports lcd_pwm_backlight] [get_bd_pins sys_ps7/TTC0_WAVE0_OUT]
  connect_bd_net -net display_rst_clk_wiz_out_peripheral_reset [get_bd_pins rst_clk_wiz_out/peripheral_reset] [get_bd_pins v_axi4s_vid_out_0/vid_io_out_reset]
  connect_bd_net -net display_rst_ps7_0_100M_peripheral_aresetn [get_bd_pins axi_cpu_interconnect/M00_ARESETN] [get_bd_pins axi_cpu_interconnect/M01_ARESETN] [get_bd_pins axi_cpu_interconnect/M02_ARESETN] [get_bd_pins axi_cpu_interconnect/M03_ARESETN] [get_bd_pins axi_vdma_0/axi_resetn] [get_bd_pins axis_subset_converter_0/aresetn] [get_bd_pins axis_subset_converter_1/aresetn] [get_bd_pins clk_wiz_0/s_axi_aresetn] [get_bd_pins rst_ps7_0_200M/peripheral_aresetn] [get_bd_pins smartconnect_0/aresetn] [get_bd_pins v_axi4s_vid_out_0/aresetn] [get_bd_pins v_tc_0/s_axi_aresetn] [get_bd_pins v_tpg_0/ap_rst_n]
  connect_bd_net -net display_v_axi4s_vid_out_0_vid_active_video [get_bd_ports lcd_de] [get_bd_ports o_video_de] [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/vid_data_enable] [get_bd_pins v_axi4s_vid_out_0/vid_active_video]
  connect_bd_net -net display_v_axi4s_vid_out_0_vid_data [get_bd_ports o_video_data] [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/vid_data_in] [get_bd_pins v_axi4s_vid_out_0/vid_data] [get_bd_pins xlslice_B/Din] [get_bd_pins xlslice_G/Din] [get_bd_pins xlslice_R/Din]
  connect_bd_net -net display_v_axi4s_vid_out_0_vid_hsync [get_bd_ports lcd_hsync] [get_bd_ports o_video_hsync] [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/vid_hsync] [get_bd_pins v_axi4s_vid_out_0/vid_hsync]
  connect_bd_net -net display_v_axi4s_vid_out_0_vid_vsync [get_bd_ports lcd_vsync] [get_bd_ports o_video_vsync] [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/vid_vsync] [get_bd_pins v_axi4s_vid_out_0/vid_vsync]
  connect_bd_net -net display_v_axi4s_vid_out_0_vtg_ce [get_bd_pins v_axi4s_vid_out_0/vtg_ce] [get_bd_pins v_tc_0/gen_clken]
  connect_bd_net -net display_v_tc_0_irq [get_bd_pins sys_concat_intc/In2] [get_bd_pins v_tc_0/irq]
  connect_bd_net -net display_v_tpg_0_interrupt [get_bd_pins sys_concat_intc/In3] [get_bd_pins v_tpg_0/interrupt]
  connect_bd_net -net display_xlslice_B_Dout [get_bd_ports lcd_data_b] [get_bd_pins xlslice_B/Dout]
  connect_bd_net -net display_xlslice_G_Dout [get_bd_ports lcd_data_g] [get_bd_pins xlslice_G/Dout]
  connect_bd_net -net display_xlslice_R_Dout [get_bd_ports lcd_data_r] [get_bd_pins xlslice_R/Dout]
  connect_bd_net -net integration_one_dout [get_bd_pins integration_one/dout] [get_bd_pins sys_ps7/SPI0_SS_I]
  connect_bd_net -net integration_zero_dout [get_bd_pins integration_zero/dout] [get_bd_pins sys_concat_intc/In4] [get_bd_pins sys_concat_intc/In5] [get_bd_pins sys_concat_intc/In6] [get_bd_pins sys_concat_intc/In7] [get_bd_pins sys_concat_intc/In8] [get_bd_pins sys_concat_intc/In9] [get_bd_pins sys_concat_intc/In10] [get_bd_pins sys_concat_intc/In11] [get_bd_pins sys_concat_intc/In14] [get_bd_pins sys_concat_intc/In15] [get_bd_pins sys_ps7/SPI0_MOSI_I] [get_bd_pins sys_ps7/SPI0_SCLK_I] [get_bd_pins v_axi4s_vid_out_0/fid] [get_bd_pins v_tpg_0/fid_in]
  connect_bd_net -net rx_clk_in_n_1 [get_bd_ports rx_clk_in_n] [get_bd_pins axi_ad9361/rx_clk_in_n]
  connect_bd_net -net rx_clk_in_p_1 [get_bd_ports rx_clk_in_p] [get_bd_pins axi_ad9361/rx_clk_in_p]
  connect_bd_net -net rx_data_in_n_1 [get_bd_ports rx_data_in_n] [get_bd_pins axi_ad9361/rx_data_in_n]
  connect_bd_net -net rx_data_in_p_1 [get_bd_ports rx_data_in_p] [get_bd_pins axi_ad9361/rx_data_in_p]
  connect_bd_net -net rx_frame_in_n_1 [get_bd_ports rx_frame_in_n] [get_bd_pins axi_ad9361/rx_frame_in_n]
  connect_bd_net -net rx_frame_in_p_1 [get_bd_ports rx_frame_in_p] [get_bd_pins axi_ad9361/rx_frame_in_p]
  connect_bd_net -net spi1_clk_i_1 [get_bd_ports spi1_clk_i] [get_bd_pins sys_ps7/SPI1_SCLK_I]
  connect_bd_net -net spi1_csn_i_1 [get_bd_ports spi1_csn_i] [get_bd_pins sys_ps7/SPI1_SS_I]
  connect_bd_net -net spi1_sdi_i_1 [get_bd_ports spi1_sdi_i] [get_bd_pins sys_ps7/SPI1_MISO_I]
  connect_bd_net -net spi1_sdo_i_1 [get_bd_ports spi1_sdo_i] [get_bd_pins sys_ps7/SPI1_MOSI_I]
  connect_bd_net -net sync_in_0_1 [get_bd_ports tdd_sync_i] [get_bd_pins util_ad9361_tdd_sync/sync_in]
  connect_bd_net -net sys_200m_clk [get_bd_pins axi_ad9361/delay_clk] [get_bd_pins axi_cpu_interconnect/M00_ACLK] [get_bd_pins axi_cpu_interconnect/M01_ACLK] [get_bd_pins axi_cpu_interconnect/M02_ACLK] [get_bd_pins axi_cpu_interconnect/M03_ACLK] [get_bd_pins axi_vdma_0/m_axi_mm2s_aclk] [get_bd_pins axi_vdma_0/m_axi_s2mm_aclk] [get_bd_pins axi_vdma_0/m_axis_mm2s_aclk] [get_bd_pins axi_vdma_0/s_axi_lite_aclk] [get_bd_pins axi_vdma_0/s_axis_s2mm_aclk] [get_bd_pins axis_subset_converter_0/aclk] [get_bd_pins axis_subset_converter_1/aclk] [get_bd_pins clk_wiz_0/s_axi_aclk] [get_bd_pins rst_ps7_0_200M/slowest_sync_clk] [get_bd_pins smartconnect_0/aclk] [get_bd_pins sys_ps7/FCLK_CLK1] [get_bd_pins sys_ps7/S_AXI_HP0_ACLK] [get_bd_pins v_axi4s_vid_out_0/aclk] [get_bd_pins v_tc_0/s_axi_aclk] [get_bd_pins v_tpg_0/ap_clk]
  connect_bd_net -net sys_concat_intc_dout [get_bd_pins sys_concat_intc/dout] [get_bd_pins sys_ps7/IRQ_F2P]
  connect_bd_net -net sys_cpu_clk [get_bd_pins axi_ad9361/s_axi_aclk] [get_bd_pins axi_ad9361_adc_dma/m_dest_axi_aclk] [get_bd_pins axi_ad9361_adc_dma/s_axi_aclk] [get_bd_pins axi_ad9361_dac_dma/m_src_axi_aclk] [get_bd_pins axi_ad9361_dac_dma/s_axi_aclk] [get_bd_pins axi_cpu_interconnect/ACLK] [get_bd_pins axi_cpu_interconnect/M04_ACLK] [get_bd_pins axi_cpu_interconnect/M05_ACLK] [get_bd_pins axi_cpu_interconnect/M06_ACLK] [get_bd_pins axi_cpu_interconnect/M07_ACLK] [get_bd_pins axi_cpu_interconnect/S00_ACLK] [get_bd_pins axi_hp1_interconnect/ACLK] [get_bd_pins axi_hp1_interconnect/M00_ACLK] [get_bd_pins axi_hp1_interconnect/S00_ACLK] [get_bd_pins axi_hp2_interconnect/ACLK] [get_bd_pins axi_hp2_interconnect/M00_ACLK] [get_bd_pins axi_hp2_interconnect/S00_ACLK] [get_bd_pins clk_wiz_0/clk_in1] [get_bd_pins sys_ps7/DMA0_ACLK] [get_bd_pins sys_ps7/FCLK_CLK0] [get_bd_pins sys_ps7/M_AXI_GP0_ACLK] [get_bd_pins sys_ps7/S_AXI_HP1_ACLK] [get_bd_pins sys_ps7/S_AXI_HP2_ACLK] [get_bd_pins sys_rstgen/slowest_sync_clk] [get_bd_pins util_ad9361_tdd_sync/clk]
  connect_bd_net -net sys_cpu_reset [get_bd_pins sys_rstgen/peripheral_reset]
  connect_bd_net -net sys_cpu_resetn [get_bd_pins axi_ad9361/s_axi_aresetn] [get_bd_pins axi_ad9361_adc_dma/m_dest_axi_aresetn] [get_bd_pins axi_ad9361_adc_dma/s_axi_aresetn] [get_bd_pins axi_ad9361_dac_dma/m_src_axi_aresetn] [get_bd_pins axi_ad9361_dac_dma/s_axi_aresetn] [get_bd_pins axi_cpu_interconnect/ARESETN] [get_bd_pins axi_cpu_interconnect/M04_ARESETN] [get_bd_pins axi_cpu_interconnect/M05_ARESETN] [get_bd_pins axi_cpu_interconnect/M06_ARESETN] [get_bd_pins axi_cpu_interconnect/M07_ARESETN] [get_bd_pins axi_cpu_interconnect/S00_ARESETN] [get_bd_pins axi_hp1_interconnect/ARESETN] [get_bd_pins axi_hp1_interconnect/M00_ARESETN] [get_bd_pins axi_hp1_interconnect/S00_ARESETN] [get_bd_pins axi_hp2_interconnect/ARESETN] [get_bd_pins axi_hp2_interconnect/M00_ARESETN] [get_bd_pins axi_hp2_interconnect/S00_ARESETN] [get_bd_pins sys_rstgen/peripheral_aresetn] [get_bd_pins util_ad9361_divclk_reset/ext_reset_in] [get_bd_pins util_ad9361_tdd_sync/rstn]
  connect_bd_net -net sys_ps7_FCLK_RESET0_N [get_bd_pins dual_pixel_24bpp_lvds_mapping_0/reset_in_n] [get_bd_pins lvds_n_x_7to1_sdr_tx_0/reset_in_n] [get_bd_pins rst_clk_wiz_out/ext_reset_in] [get_bd_pins rst_ps7_0_200M/ext_reset_in] [get_bd_pins sys_ps7/FCLK_RESET0_N] [get_bd_pins sys_rstgen/ext_reset_in]
  connect_bd_net -net sys_ps7_GPIO_O [get_bd_ports gpio_o] [get_bd_pins sys_ps7/GPIO_O]
  connect_bd_net -net sys_ps7_GPIO_T [get_bd_ports gpio_t] [get_bd_pins sys_ps7/GPIO_T]
  connect_bd_net -net sys_ps7_SPI1_MOSI_O [get_bd_ports spi1_sdo_o] [get_bd_pins sys_ps7/SPI1_MOSI_O]
  connect_bd_net -net sys_ps7_SPI1_SCLK_O [get_bd_ports spi1_clk_o] [get_bd_pins sys_ps7/SPI1_SCLK_O]
  connect_bd_net -net sys_ps7_SPI1_SS1_O [get_bd_ports spi1_csn_1_o] [get_bd_pins sys_ps7/SPI1_SS1_O]
  connect_bd_net -net sys_ps7_SPI1_SS2_O [get_bd_ports spi1_csn_2_o] [get_bd_pins sys_ps7/SPI1_SS2_O]
  connect_bd_net -net sys_ps7_SPI1_SS_O [get_bd_ports spi1_csn_0_o] [get_bd_pins sys_ps7/SPI1_SS_O]
  connect_bd_net -net up_enable_1 [get_bd_ports up_enable] [get_bd_pins axi_ad9361/up_enable]
  connect_bd_net -net up_txnrx_1 [get_bd_ports up_txnrx] [get_bd_pins axi_ad9361/up_txnrx]
  connect_bd_net -net util_ad9361_adc_fifo_din_ovf [get_bd_pins axi_ad9361/adc_dovf] [get_bd_pins util_ad9361_adc_fifo/din_ovf]
  connect_bd_net -net util_ad9361_adc_fifo_dout_data_0 [get_bd_pins util_ad9361_adc_fifo/dout_data_0] [get_bd_pins util_ad9361_adc_pack/adc_data_0]
  connect_bd_net -net util_ad9361_adc_fifo_dout_data_1 [get_bd_pins util_ad9361_adc_fifo/dout_data_1] [get_bd_pins util_ad9361_adc_pack/adc_data_1]
  connect_bd_net -net util_ad9361_adc_fifo_dout_data_2 [get_bd_pins util_ad9361_adc_fifo/dout_data_2] [get_bd_pins util_ad9361_adc_pack/adc_data_2]
  connect_bd_net -net util_ad9361_adc_fifo_dout_data_3 [get_bd_pins util_ad9361_adc_fifo/dout_data_3] [get_bd_pins util_ad9361_adc_pack/adc_data_3]
  connect_bd_net -net util_ad9361_adc_fifo_dout_enable_0 [get_bd_pins util_ad9361_adc_fifo/dout_enable_0] [get_bd_pins util_ad9361_adc_pack/adc_enable_0]
  connect_bd_net -net util_ad9361_adc_fifo_dout_enable_1 [get_bd_pins util_ad9361_adc_fifo/dout_enable_1] [get_bd_pins util_ad9361_adc_pack/adc_enable_1]
  connect_bd_net -net util_ad9361_adc_fifo_dout_enable_2 [get_bd_pins util_ad9361_adc_fifo/dout_enable_2] [get_bd_pins util_ad9361_adc_pack/adc_enable_2]
  connect_bd_net -net util_ad9361_adc_fifo_dout_enable_3 [get_bd_pins util_ad9361_adc_fifo/dout_enable_3] [get_bd_pins util_ad9361_adc_pack/adc_enable_3]
  connect_bd_net -net util_ad9361_adc_fifo_dout_valid_0 [get_bd_pins util_ad9361_adc_fifo/dout_valid_0] [get_bd_pins util_ad9361_adc_pack/adc_valid_0]
  connect_bd_net -net util_ad9361_adc_fifo_dout_valid_1 [get_bd_pins util_ad9361_adc_fifo/dout_valid_1] [get_bd_pins util_ad9361_adc_pack/adc_valid_1]
  connect_bd_net -net util_ad9361_adc_fifo_dout_valid_2 [get_bd_pins util_ad9361_adc_fifo/dout_valid_2] [get_bd_pins util_ad9361_adc_pack/adc_valid_2]
  connect_bd_net -net util_ad9361_adc_fifo_dout_valid_3 [get_bd_pins util_ad9361_adc_fifo/dout_valid_3] [get_bd_pins util_ad9361_adc_pack/adc_valid_3]
  connect_bd_net -net util_ad9361_adc_pack_adc_data [get_bd_pins axi_ad9361_adc_dma/fifo_wr_din] [get_bd_pins util_ad9361_adc_pack/adc_data]
  connect_bd_net -net util_ad9361_adc_pack_adc_sync [get_bd_pins axi_ad9361_adc_dma/fifo_wr_sync] [get_bd_pins util_ad9361_adc_pack/adc_sync]
  connect_bd_net -net util_ad9361_adc_pack_adc_valid [get_bd_pins axi_ad9361_adc_dma/fifo_wr_en] [get_bd_pins util_ad9361_adc_pack/adc_valid]
  connect_bd_net -net util_ad9361_dac_upack_dac_data_0 [get_bd_pins axi_ad9361_dac_fifo/din_data_0] [get_bd_pins util_ad9361_dac_upack/dac_data_0]
  connect_bd_net -net util_ad9361_dac_upack_dac_data_1 [get_bd_pins axi_ad9361_dac_fifo/din_data_1] [get_bd_pins util_ad9361_dac_upack/dac_data_1]
  connect_bd_net -net util_ad9361_dac_upack_dac_data_2 [get_bd_pins axi_ad9361_dac_fifo/din_data_2] [get_bd_pins util_ad9361_dac_upack/dac_data_2]
  connect_bd_net -net util_ad9361_dac_upack_dac_data_3 [get_bd_pins axi_ad9361_dac_fifo/din_data_3] [get_bd_pins util_ad9361_dac_upack/dac_data_3]
  connect_bd_net -net util_ad9361_dac_upack_dac_valid [get_bd_pins axi_ad9361_dac_dma/fifo_rd_en] [get_bd_pins util_ad9361_dac_upack/dac_valid]
  connect_bd_net -net util_ad9361_dac_upack_dac_valid_out_0 [get_bd_pins axi_ad9361_dac_fifo/din_valid_in_0] [get_bd_pins util_ad9361_dac_upack/dac_valid_out_0]
  connect_bd_net -net util_ad9361_dac_upack_dac_valid_out_1 [get_bd_pins axi_ad9361_dac_fifo/din_valid_in_1] [get_bd_pins util_ad9361_dac_upack/dac_valid_out_1]
  connect_bd_net -net util_ad9361_dac_upack_dac_valid_out_2 [get_bd_pins axi_ad9361_dac_fifo/din_valid_in_2] [get_bd_pins util_ad9361_dac_upack/dac_valid_out_2]
  connect_bd_net -net util_ad9361_dac_upack_dac_valid_out_3 [get_bd_pins axi_ad9361_dac_fifo/din_valid_in_3] [get_bd_pins util_ad9361_dac_upack/dac_valid_out_3]
  connect_bd_net -net util_ad9361_divclk_clk_out [get_bd_pins axi_ad9361_adc_dma/fifo_wr_clk] [get_bd_pins axi_ad9361_dac_dma/fifo_rd_clk] [get_bd_pins axi_ad9361_dac_fifo/din_clk] [get_bd_pins util_ad9361_adc_fifo/dout_clk] [get_bd_pins util_ad9361_adc_pack/adc_clk] [get_bd_pins util_ad9361_dac_upack/dac_clk] [get_bd_pins util_ad9361_divclk/clk_out] [get_bd_pins util_ad9361_divclk_reset/slowest_sync_clk]
  connect_bd_net -net util_ad9361_divclk_reset_peripheral_aresetn [get_bd_pins axi_ad9361_dac_fifo/din_rstn] [get_bd_pins util_ad9361_adc_fifo/dout_rstn] [get_bd_pins util_ad9361_divclk_reset/peripheral_aresetn]
  connect_bd_net -net util_ad9361_divclk_reset_peripheral_reset [get_bd_pins util_ad9361_adc_pack/adc_rst] [get_bd_pins util_ad9361_divclk_reset/peripheral_reset]
  connect_bd_net -net util_ad9361_divclk_sel_Res [get_bd_pins util_ad9361_divclk/clk_sel] [get_bd_pins util_ad9361_divclk_sel/Res]
  connect_bd_net -net util_ad9361_divclk_sel_concat_dout [get_bd_pins util_ad9361_divclk_sel/Op1] [get_bd_pins util_ad9361_divclk_sel_concat/dout]
  connect_bd_net -net util_ad9361_tdd_sync_sync_out [get_bd_ports tdd_sync_o] [get_bd_pins axi_ad9361/tdd_sync] [get_bd_pins util_ad9361_tdd_sync/sync_out]

  # Create address segments
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_ad9361_adc_dma/m_dest_axi] [get_bd_addr_segs sys_ps7/S_AXI_HP1/HP1_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_ad9361_dac_dma/m_src_axi] [get_bd_addr_segs sys_ps7/S_AXI_HP2/HP2_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_MM2S] [get_bd_addr_segs sys_ps7/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x00000000 -range 0x40000000 -target_address_space [get_bd_addr_spaces axi_vdma_0/Data_S2MM] [get_bd_addr_segs sys_ps7/S_AXI_HP0/HP0_DDR_LOWOCM] -force
  assign_bd_address -offset 0x7C400000 -range 0x00001000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs axi_ad9361_adc_dma/s_axi/axi_lite] -force
  assign_bd_address -offset 0x79020000 -range 0x00010000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs axi_ad9361/s_axi/axi_lite] -force
  assign_bd_address -offset 0x7C420000 -range 0x00001000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs axi_ad9361_dac_dma/s_axi/axi_lite] -force
  assign_bd_address -offset 0x43000000 -range 0x00010000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs axi_vdma_0/S_AXI_LITE/Reg] -force
  assign_bd_address -offset 0x43C10000 -range 0x00010000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs clk_wiz_0/s_axi_lite/Reg] -force
  assign_bd_address -offset 0x43C20000 -range 0x00010000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs v_tc_0/ctrl/Reg] -force
  assign_bd_address -offset 0x43C00000 -range 0x00010000 -target_address_space [get_bd_addr_spaces sys_ps7/Data] [get_bd_addr_segs v_tpg_0/s_axi_CTRL/Reg] -force


  # Restore current instance
  current_bd_instance $oldCurInst

  validate_bd_design
  save_bd_design
}
# End of create_root_design()


##################################################################
# MAIN FLOW
##################################################################

create_root_design ""


