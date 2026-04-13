; MIRROR4FREE Installer (NSIS)
; Installs official Python + app source - no PyInstaller

!include "MUI2.nsh"

Name "MIRROR4FREE"
OutFile "..\dist\MIRROR4FREE-Setup.exe"
InstallDir "$PROGRAMFILES\MIRROR4FREE"
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
    File /r "..\dist\MIRROR4FREE\*.*"

    ; Install assets (icon, images, etc.)
    SetOutPath "$INSTDIR\assets"
    File /r "..\assets\*.*"
    SetOutPath "$INSTDIR"

    ; Remove Mark of the Web from all binaries
    nsExec::ExecToLog 'powershell -ExecutionPolicy Bypass -Command "Get-ChildItem -Path $INSTDIR -Recurse -Include *.dll,*.pyd,*.exe | Unblock-File"'

    ; Desktop shortcut with icon
    CreateShortCut "$DESKTOP\MIRROR4FREE.lnk" "$INSTDIR\MIRROR4FREE.exe" "" "$INSTDIR\assets\icon.ico"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\MIRROR4FREE"
    CreateShortCut "$SMPROGRAMS\MIRROR4FREE\MIRROR4FREE.lnk" "$INSTDIR\MIRROR4FREE.exe" "" "$INSTDIR\assets\icon.ico"
    CreateShortCut "$SMPROGRAMS\MIRROR4FREE\Debug Mode.lnk" "$INSTDIR\debug.bat"
    CreateShortCut "$SMPROGRAMS\MIRROR4FREE\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE" "DisplayName" "MIRROR4FREE"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE" "DisplayIcon" "$INSTDIR\assets\icon.ico"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE" "Publisher" "MIRROR4FREE"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\MIRROR4FREE"
    Delete "$DESKTOP\MIRROR4FREE.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MIRROR4FREE"
SectionEnd
