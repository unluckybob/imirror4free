; IMIRROR4FREE — NSIS Installer
; Uses Python embeddable distribution (signed DLLs from python.org)

!include "MUI2.nsh"

Unicode True

Name "IMIRROR4FREE"
OutFile "..\dist\IMIRROR4FREE-Setup.exe"
InstallDir "$PROGRAMFILES64\IMIRROR4FREE"
RequestExecutionLevel admin

; Modern UI
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"

; Installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\python\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS '"$INSTDIR\run.py"'
!define MUI_FINISHPAGE_RUN_TEXT "Launch IMIRROR4FREE"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ─── Install ──────────────────────────────────────────────
Section "Install"
  SetOutPath "$INSTDIR"

  ; Copy all application files (python/, imirror/, run.py, debug.bat)
  File /r "..\dist\IMIRROR4FREE\*.*"

  ; Desktop shortcut — pythonw.exe = no console window
  SetOutPath "$INSTDIR"
  CreateShortcut "$DESKTOP\IMIRROR4FREE.lnk" \
    "$INSTDIR\python\pythonw.exe" \
    '"$INSTDIR\run.py"' \
    "$INSTDIR\python\pythonw.exe" 0

  ; Start Menu
  CreateDirectory "$SMPROGRAMS\IMIRROR4FREE"
  CreateShortcut "$SMPROGRAMS\IMIRROR4FREE\IMIRROR4FREE.lnk" \
    "$INSTDIR\python\pythonw.exe" \
    '"$INSTDIR\run.py"' \
    "$INSTDIR\python\pythonw.exe" 0
  CreateShortcut "$SMPROGRAMS\IMIRROR4FREE\Debug Mode.lnk" \
    "$INSTDIR\debug.bat" \
    "" \
    "$INSTDIR\python\python.exe" 0
  CreateShortcut "$SMPROGRAMS\IMIRROR4FREE\Uninstall.lnk" \
    "$INSTDIR\uninstall.exe"

  ; Uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Add/Remove Programs registry
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "DisplayName" "IMIRROR4FREE — iPhone Screen Mirroring"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "Publisher" "IMIRROR4FREE"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" \
    "NoRepair" 1
SectionEnd

; ─── Uninstall ────────────────────────────────────────────
Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$DESKTOP\IMIRROR4FREE.lnk"
  RMDir /r "$SMPROGRAMS\IMIRROR4FREE"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE"
SectionEnd
