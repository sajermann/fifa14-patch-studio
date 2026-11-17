; NSIS hooks of the FIFA 14 Patch Studio installer (Tauri installerHooks).
; The app keeps its data (settings, basket, saved selections, exported packages) in data\ inside the app folder:
; removed only when the "delete app data" checkbox is checked, never on updates.
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    RmDir /r "$INSTDIR\data"
    RmDir "$INSTDIR"
  ${EndIf}
!macroend
