"""Isolated P201 UART0/EMIO candidate transforms. Never deploys a board image."""
import re

UART_BD = '''
# P201 external UART candidate: UART1 MIO12/13 remains the debug console.
ad_ip_parameter sys_ps7 CONFIG.PCW_UART0_PERIPHERAL_ENABLE 1
ad_ip_parameter sys_ps7 CONFIG.PCW_UART0_UART0_IO EMIO
create_bd_port -dir O ext_uart_tx
create_bd_port -dir I ext_uart_rx
ad_connect ext_uart_tx sys_ps7/UART0_TX
ad_connect ext_uart_rx sys_ps7/UART0_RX
'''
UART_XDC = '''
# CANDIDATE ONLY. J19 5=E17 TX; 6=E18 RX; separate verified GND.
set_property -dict {PACKAGE_PIN E17 IOSTANDARD LVCMOS33} [get_ports ext_uart_tx]
set_property -dict {PACKAGE_PIN E18 IOSTANDARD LVCMOS33} [get_ports ext_uart_rx]
'''

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('ambiguous or changed source anchor')
    return text.replace(old,new,1)

def candidate_sources(bd,top,xdc):
    if 'CONFIG.PCW_UART1_UART1_IO "MIO 12 .. 13"' not in bd:
        raise ValueError('original UART1 console configuration required')
    if re.search(r'PCW_UART0|ext_uart_',bd+top+xdc):
        raise ValueError('UART0 or external UART already configured')
    used=set(re.findall(r'PACKAGE_PIN\s+(\w+)',xdc))
    if used & {'E17','E18'}:raise ValueError('candidate package pin occupied')
    top=once(top,'module system_top (','module system_top (\n  output ext_uart_tx,\n  input ext_uart_rx,')
    top=once(top,'system_wrapper i_system_wrapper (',
             'system_wrapper i_system_wrapper (\n    .ext_uart_tx (ext_uart_tx),\n    .ext_uart_rx (ext_uart_rx),')
    return bd+UART_BD,top,xdc+UART_XDC

def enabled_dts(source):
    """Enable UART0 and explicitly preserve UART1 as ttyPS0 in this offline DTB."""
    if len(re.findall(r'\bserial@e0000000\s*\{',source))!=1:
        raise ValueError('unique vendor UART0 required')
    if not re.search(r'\bamba\s*\{',source):raise ValueError('expected actual /amba bus')
    if not re.search(r'\bserial@e0001000\s*\{',source):raise ValueError('UART1 required')
    if re.search(r'\bserial1\s*=',source):raise ValueError('second serial alias already present')
    return source+'''
// Candidate: actual nodes are /amba, not the vendor's stale /axi aliases.
/ {
    aliases {
        serial0 = "/amba/serial@e0001000";
        serial1 = "/amba/serial@e0000000";
    };
    chosen { stdout-path = "/amba/serial@e0001000:115200n8"; };
};
&{/amba/serial@e0000000} { status = "okay"; };
'''
