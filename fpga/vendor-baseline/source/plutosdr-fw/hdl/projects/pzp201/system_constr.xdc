
# constraints
# ad9361

set_property  -dict {PACKAGE_PIN  P18  IOSTANDARD LVCMOS18} [get_ports gpio_en_agc]                       ; 
set_property  -dict {PACKAGE_PIN  W19  IOSTANDARD LVCMOS18} [get_ports gpio_resetb]                       ; 

set_property  -dict {PACKAGE_PIN  V8  IOSTANDARD LVCMOS18} [get_ports gpio_ctl[0]]                       ; 
set_property  -dict {PACKAGE_PIN  W8  IOSTANDARD LVCMOS18} [get_ports gpio_ctl[1]]                       ; 
set_property  -dict {PACKAGE_PIN  W10 IOSTANDARD LVCMOS18} [get_ports gpio_ctl[2]]                       ; 
set_property  -dict {PACKAGE_PIN  W9  IOSTANDARD LVCMOS18} [get_ports gpio_ctl[3]]                       ; 
set_property  -dict {PACKAGE_PIN  U7  IOSTANDARD LVCMOS18} [get_ports gpio_status[0]]                    ; 
set_property  -dict {PACKAGE_PIN  V7  IOSTANDARD LVCMOS18} [get_ports gpio_status[1]]                    ; 
set_property  -dict {PACKAGE_PIN  T9  IOSTANDARD LVCMOS18} [get_ports gpio_status[2]]                    ; 
set_property  -dict {PACKAGE_PIN  U10 IOSTANDARD LVCMOS18} [get_ports gpio_status[3]]                    ; 
set_property  -dict {PACKAGE_PIN  Y7  IOSTANDARD LVCMOS18} [get_ports gpio_status[4]]                    ; 
set_property  -dict {PACKAGE_PIN  Y6  IOSTANDARD LVCMOS18} [get_ports gpio_status[5]]                    ; 
set_property  -dict {PACKAGE_PIN  Y9  IOSTANDARD LVCMOS18} [get_ports gpio_status[6]]                    ; 
set_property  -dict {PACKAGE_PIN  Y8  IOSTANDARD LVCMOS18} [get_ports gpio_status[7]]                    ; 

set_property  -dict {PACKAGE_PIN  N18  IOSTANDARD LVCMOS18} [get_ports rx_clk_in]       ; 
set_property  -dict {PACKAGE_PIN  R16  IOSTANDARD LVCMOS18} [get_ports rx_frame_in]     ; 
set_property  -dict {PACKAGE_PIN  V17  IOSTANDARD LVCMOS18} [get_ports rx_data_in[1]]   ; 
set_property  -dict {PACKAGE_PIN  V18  IOSTANDARD LVCMOS18} [get_ports rx_data_in[0]]   ; 
set_property  -dict {PACKAGE_PIN  Y18  IOSTANDARD LVCMOS18} [get_ports rx_data_in[3]]   ; 
set_property  -dict {PACKAGE_PIN  Y19  IOSTANDARD LVCMOS18} [get_ports rx_data_in[2]]   ; 
set_property  -dict {PACKAGE_PIN  T17  IOSTANDARD LVCMOS18} [get_ports rx_data_in[5]]   ; 
set_property  -dict {PACKAGE_PIN  R18  IOSTANDARD LVCMOS18} [get_ports rx_data_in[4]]   ; 
set_property  -dict {PACKAGE_PIN  V20  IOSTANDARD LVCMOS18} [get_ports rx_data_in[7]]   ; 
set_property  -dict {PACKAGE_PIN  W20  IOSTANDARD LVCMOS18} [get_ports rx_data_in[6]]   ; 
set_property  -dict {PACKAGE_PIN  T20  IOSTANDARD LVCMOS18} [get_ports rx_data_in[9]]   ; 
set_property  -dict {PACKAGE_PIN  U20  IOSTANDARD LVCMOS18} [get_ports rx_data_in[8]]   ; 
set_property  -dict {PACKAGE_PIN  V16  IOSTANDARD LVCMOS18} [get_ports rx_data_in[11]]   ; 
set_property  -dict {PACKAGE_PIN  W16  IOSTANDARD LVCMOS18} [get_ports rx_data_in[10]]   ; 

set_property  -dict {PACKAGE_PIN  U14  IOSTANDARD LVCMOS18}  [get_ports tx_clk_out]                      ; 
set_property  -dict {PACKAGE_PIN  V15  IOSTANDARD LVCMOS18}  [get_ports tx_frame_out]                    ; 
set_property  -dict {PACKAGE_PIN  P14  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[1]]                  ; 
set_property  -dict {PACKAGE_PIN  R14  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[0]]                  ; 
set_property  -dict {PACKAGE_PIN  V12  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[3]]                  ; 
set_property  -dict {PACKAGE_PIN  W13  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[2]]                  ; 
set_property  -dict {PACKAGE_PIN  W14  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[5]]                  ; 
set_property  -dict {PACKAGE_PIN  Y14  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[4]]                  ; 
set_property  -dict {PACKAGE_PIN  T14  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[7]]                  ; 
set_property  -dict {PACKAGE_PIN  T15  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[6]]                  ; 
set_property  -dict {PACKAGE_PIN  Y16  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[9]]                  ; 
set_property  -dict {PACKAGE_PIN  Y17  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[8]]                  ; 
set_property  -dict {PACKAGE_PIN  T16  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[11]]                  ; 
set_property  -dict {PACKAGE_PIN  U17  IOSTANDARD LVCMOS18}  [get_ports tx_data_out[10]]                  ; 


set_property  -dict {PACKAGE_PIN  P16  IOSTANDARD LVCMOS18} [get_ports txnrx]                             ; 
set_property  -dict {PACKAGE_PIN  N17  IOSTANDARD LVCMOS18} [get_ports enable]                            ; 


set_property  -dict {PACKAGE_PIN  T10  IOSTANDARD LVCMOS18  PULLTYPE PULLUP} [get_ports spi_csn]          ; 
set_property  -dict {PACKAGE_PIN  T11  IOSTANDARD LVCMOS18} [get_ports spi_clk]                           ; 
set_property  -dict {PACKAGE_PIN  T12  IOSTANDARD LVCMOS18} [get_ports spi_mosi]                          ; 
set_property  -dict {PACKAGE_PIN  U12  IOSTANDARD LVCMOS18} [get_ports spi_miso]                          ; 

# spi pmod JA1
set_property  -dict {PACKAGE_PIN W11 IOSTANDARD LVCMOS18} [get_ports pl_spi_clk_o]                        ; 
set_property  -dict {PACKAGE_PIN U9  IOSTANDARD LVCMOS18} [get_ports pl_spi_miso]                         ; 
set_property  -dict {PACKAGE_PIN U8  IOSTANDARD LVCMOS18} [get_ports pl_spi_mosi]                         ; 
set_property  -dict {PACKAGE_PIN T5  IOSTANDARD LVCMOS18} [get_ports iic_scl]                             ; 
set_property  -dict {PACKAGE_PIN U5  IOSTANDARD LVCMOS18} [get_ports iic_sda]                             ; 


# clocks
create_clock -name rx_clk -period  16.27 [get_ports rx_clk_in]



