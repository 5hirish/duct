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
  ; $R5-$R8, not $R0: the template's shortcut functions called below use $R0 and $0.
  ReadRegStr $R5 HKLM "${UNINSTKEY}" "InstallLocation"
  ; Stored quoted, as "C:\Program Files\Duct".
  StrCpy $R6 $R5 1
  ${If} $R6 == '"'
    StrCpy $R5 $R5 "" 1
    StrCpy $R5 $R5 -1
  ${EndIf}
  ${If} $R5 != ""
  ${AndIf} $R5 != $INSTDIR
  ${AndIf} ${FileExists} "$R5\uninstall.exe"
    ; Read before its uninstaller removes it: did the old copy have a desktop
    ; shortcut (on the Public desktop, as a per-machine install puts it)?
    SetShellVarContext all
    StrCpy $R7 0
    ${If} ${FileExists} "$DESKTOP\${PRODUCTNAME}.lnk"
      StrCpy $R7 1
    ${EndIf}
    SetShellVarContext current
    ExecShellWait "runas" "$SYSDIR\cmd.exe" '/c ""$R5\uninstall.exe" /S _?=$R5 & del /f /q "$R5\uninstall.exe" & rmdir "$R5""' SW_HIDE
    ; An update run (/UPDATE) creates no shortcuts of its own: it trusts the
    ; install it updates to have them. The copy just retired took its shortcuts
    ; with it, so without these the only way back into Duct after this update
    ; is the relaunch it ends with; the Start menu and Windows search lose it.
    ; Only once the old copy is gone: a declined prompt keeps its shortcuts, and
    ; two Start menu entries would open two different versions.
    ${IfNot} ${FileExists} "$R5\uninstall.exe"
      StrCpy $R8 $UpdateMode
      StrCpy $UpdateMode 0
      Call CreateOrUpdateStartMenuShortcut
      ${If} $R7 = 1
        Call CreateOrUpdateDesktopShortcut
      ${EndIf}
      StrCpy $UpdateMode $R8
    ${EndIf}
  ${EndIf}
!macroend
