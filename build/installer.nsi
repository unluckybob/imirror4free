; MIRANCE Installer (NSIS)
; Installs official Python + app source - no PyInstaller

!include "MUI2.nsh"

Name "MIRANCE"
OutFile "..\dist\MIRANCE-Setup.exe"
InstallDir "$PROGRAMFILES\MIRANCE"
RequestExecutionLevel admin

; Installer / Uninstaller icons
Icon "..\assets\icon.ico"
UninstallIcon "..\assets\icon.ico"

; MUI icon settings
!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"

; MUI header image (optional branding)
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT

; MUI abort warning
!define MUI_ABORTWARNING

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
    File /r "..\dist\MIRANCE\*.*"

    ; Install assets (icon, images, etc.)
    SetOutPath "$INSTDIR\assets"
    File /r "..\assets\*.*"
    SetOutPath "$INSTDIR"

    ; Remove Mark of the Web from all binaries
    nsExec::ExecToLog 'powershell -ExecutionPolicy Bypass -Command "Get-ChildItem -Path $INSTDIR -Recurse -Include *.dll,*.pyd,*.exe | Unblock-File"'

    ; Desktop shortcut with icon
    CreateShortCut "$DESKTOP\MIRANCE.lnk" "$INSTDIR\MIRANCE.exe" "" "$INSTDIR\assets\icon.ico"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\MIRANCE"
    CreateShortCut "$SMPROGRAMS\MIRANCE\MIRANCE.lnk" "$INSTDIR\MIRANCE.exe" "" "$INSTDIR\assets\icon.ico"
    CreateShortCut "$SMPROGRAMS\MIRANCE\Debug Mode.lnk" "$INSTDIR\debug.bat"
    CreateShortCut "$SMPROGRAMS\MIRANCE\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE" "DisplayName" "MIRANCE"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE" "DisplayIcon" "$INSTDIR\assets\icon.ico"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE" "Publisher" "MIRANCE"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\MIRANCE"
    Delete "$DESKTOP\MIRANCE.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRANCE"
SectionEnd
