; IMIRROR4FREE NSIS Installer Script
; Modeled after AnyMiro's NSIS installer structure
; Installs to Program Files so Windows trusts all DLLs

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ─── App metadata ───
!define PRODUCT_NAME "IMIRROR4FREE"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "IMIRROR4FREE"
!define PRODUCT_WEB_SITE "https://github.com/unluckybob/imirror4free"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\IMIRROR4FREE.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; ─── Installer config ───
Name "${PRODUCT_NAME}"
OutFile "IMIRROR4FREE-Setup.exe"
InstallDir "$PROGRAMFILES\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show
SetCompressor /SOLID lzma

; ─── Modern UI config ───
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${PRODUCT_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install ${PRODUCT_NAME} on your computer.$\r$\n$\r$\n${PRODUCT_NAME} provides free iPhone USB screen mirroring with the highest quality and lowest latency.$\r$\n$\r$\nClick Next to continue."

; ─── Pages ───
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_INSTFILES

; ─── Language ───
!insertmacro MUI_LANGUAGE "English"

; ─── Install section ───
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite on

    ; Copy ALL files from the PyInstaller onedir output
    ; The /r flag recursively copies everything including _internal/
    File /r "dist\IMIRROR4FREE\*.*"

    ; Remove Zone.Identifier from all files (removes Mark of the Web)
    ; This is the key fix — Windows won't block DLLs without MOTW
    nsExec::ExecToLog 'powershell -Command "Get-ChildItem -Path $\"$INSTDIR$\" -Recurse | Unblock-File"'

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\IMIRROR4FREE.exe"
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\IMIRROR4FREE.exe"
SectionEnd

; ─── Post-install: registry + uninstaller ───
Section -Post
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; App Paths registry (so Windows can find the exe)
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\IMIRROR4FREE.exe"

    ; Add/Remove Programs entry
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\IMIRROR4FREE.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

; ─── Uninstaller ───
Section Uninstall
    ; Remove shortcuts
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

    ; Remove installed files
    RMDir /r "$INSTDIR"

    ; Remove registry entries
    DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    SetAutoClose true
SectionEnd
