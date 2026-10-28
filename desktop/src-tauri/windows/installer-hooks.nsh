; Duct's hooks into Tauri's NSIS installer template
; (`bundle.windows.nsis.installerHooks` in tauri.conf.json). The template
; includes this file near its top and expands each macro at its hook point.

; Retire a per-machine install left by Duct 0.7.1 or earlier.
;
; Those versions installed per machine (Program Files, admin rights), so every
; self-update raised a UAC prompt for an unsigned publisher. From 0.7.2 Duct
; installs per user and never needs admin. An update to an old install
; therefore lands beside it, in %LOCALAPPDATA%, and this removes the old copy:
; one last admin prompt, then none. Declining it leaves both copies working,
; and the old one is offered again at its next update.
;
; Nothing the user owns is touched. Their data was always per user (the
; webview store under %LOCALAPPDATA%\<bundle id>, keys in Credential Manager),
; and the old uninstaller runs silently, which leaves its "delete app data"
; box unticked. `_?=` makes it run in place so this waits for it; it cannot
; delete itself while running, so its file and the then-empty folder are
; removed after it. `rmdir` without /s only removes an empty folder: the old
; install could have been put in a folder of the user's choosing.
!macro NSIS_HOOK_POSTINSTALL
  ReadRegStr $R0 HKLM "${UNINSTKEY}" "InstallLocation"
  ; Stored quoted, as "C:\Program Files\Duct".
  StrCpy $R1 $R0 1
  ${If} $R1 == '"'
    StrCpy $R0 $R0 "" 1
    StrCpy $R0 $R0 -1
  ${EndIf}
  ${If} $R0 != ""
  ${AndIf} $R0 != $INSTDIR
  ${AndIf} ${FileExists} "$R0\uninstall.exe"
    ExecShellWait "runas" "$SYSDIR\cmd.exe" '/c ""$R0\uninstall.exe" /S _?=$R0 & del /f /q "$R0\uninstall.exe" & rmdir "$R0""' SW_HIDE
  ${EndIf}
!macroend
