; IMIRROR4FREE Installer (NSIS)
; Installs official Python + app source - no PyInstaller

!include "MUI2.nsh"

Name "IMIRROR4FREE"
OutFile "..\dist\IMIRROR4FREE-Setup.exe"
InstallDir "$PROGRAMFILES\IMIRROR4FREE"
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
    File /r "..\dist\IMIRROR4FREE\*.*"

    ; Install assets (icon, images, etc.)
    SetOutPath "$INSTDIR\assets"
    File /r "..\assets\*.*"
    SetOutPath "$INSTDIR"

    ; Remove Mark of the Web from all binaries
    nsExec::ExecToLog 'powershell -ExecutionPolicy Bypass -Command "Get-ChildItem -Path $INSTDIR -Recurse -Include *.dll,*.pyd,*.exe | Unblock-File"'

    ; Desktop shortcut with icon
    CreateShortCut "$DESKTOP\IMIRROR4FREE.lnk" "$INSTDIR\IMIRROR4FREE.exe" "" "$INSTDIR\assets\icon.ico"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\IMIRROR4FREE"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\IMIRROR4FREE.lnk" "$INSTDIR\IMIRROR4FREE.exe" "" "$INSTDIR\assets\icon.ico"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\Debug Mode.lnk" "$INSTDIR\debug.bat"
    CreateShortCut "$SMPROGRAMS\IMIRROR4FREE\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "DisplayName" "IMIRROR4FREE"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "DisplayIcon" "$INSTDIR\assets\icon.ico"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE" "Publisher" "IMIRROR4FREE"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\IMIRROR4FREE"
    Delete "$DESKTOP\IMIRROR4FREE.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\IMIRROR4FREE"
SectionEnd
