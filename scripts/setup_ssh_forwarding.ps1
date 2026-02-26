# WSL SSH Port Forwarding Script for Windows
# Run this in PowerShell as Administrator

$wsl_ip = wsl -d Ubuntu -e ip addr show eth0 | Select-String "inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})" | ForEach-Object { $_.Matches.Groups[1].Value }

if ($wsl_ip) {
    Write-Host "Found WSL IP: $wsl_ip"
    
    # 2222 port to WSL 22 port
    $addr_listen = "0.0.0.0"
    $port_listen = 2222
    $port_connect = 22
    
    # Clear existing proxy
    netsh interface portproxy reset
    
    # Add new proxy
    netsh interface portproxy add v4tov4 listenaddress=$addr_listen listenport=$port_listen connectaddress=$wsl_ip connectport=$port_connect
    
    # Firewall Rule
    # Remove existing if exists
    Remove-NetFirewallRule -DisplayName "WSL SSH" -ErrorAction SilentlyContinue
    # Add new rule
    New-NetFirewallRule -DisplayName "WSL SSH" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port_listen
    
    Write-Host "Port forwarding set: Windows:$port_listen -> WSL:$port_connect ($wsl_ip)"
    Write-Host "Connect from your phone using [Windows_IP]:$port_listen"
} else {
    Write-Error "Could not find WSL IP address."
}
