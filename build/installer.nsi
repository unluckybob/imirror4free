; IMIRROR4FREE Installer (NSIS)
; Installs official Python + app source - no PyInstaller

!include "MUI2.nsh"

Name "IMIRROR4FREE"
OutFile "..\dist\IMIRROR4FREE-Setup.exe"
InstallDir "$PROGRAMFILES\IMIRROR4FREE"
RequestExecutionLevel admin

; Pages
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"

    ; Install all files recursively
    File /r "..\dist\IMIRROR4FREE\*.*"

    ; Remove Mark of the Web from all binaries
    nsExec::ExecToLog 'powershell -ExecutionPolicy Bypass -Command "Get-ChildItem -Path $INSTDIR -Recurse -Include *.dll,*.pyd,*.exe | Unblock-File"'

    ; Desktop shortcut
    CreateShortCut "$DESKTOP\IMIRROR4FREE.lnk" "$INSTDIR\IMIRROR4FREE.exe"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\IMIRROR4FREE"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\IMIRROR4FREE.lnk" "$INSTDIR\IMIRROR4FREE.exe"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\Debug Mode.lnk" "$INSTDIR\debug.bat"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "DisplayName" "IMIRROR4FREE"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\IMIRROR4FREE"
    Delete "$DESKTOP\IMIRROR4FREE.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE"
SectionEnd
