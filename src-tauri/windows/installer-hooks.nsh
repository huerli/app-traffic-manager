!macro FlowStopProcesses
  DetailPrint "Stopping Flow desktop and background processes..."
  nsExec::ExecToLog 'taskkill /F /T /IM "flow-traffic-manager.exe"'
  Pop $0
  nsExec::ExecToLog 'taskkill /F /T /IM "flow-backend.exe"'
  Pop $0
  ; Give Windows time to release executable and log handles before replacing files.
  Sleep 500
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro FlowStopProcesses
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro FlowStopProcesses
!macroend
