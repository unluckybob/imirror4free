/*
 * IMIRANCE Launcher
 * Tiny native exe that launches the real Python app.
 * Python DLLs are from python.org (signed by PSF) so Windows trusts them.
 * Compiled with MSVC in GitHub Actions - no PyInstaller needed.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrev, LPSTR lpCmd, int nShow) {
    char exeDir[MAX_PATH];
    char cmdLine[MAX_PATH * 2];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;

    /* Get directory containing this exe */
    GetModuleFileNameA(NULL, exeDir, MAX_PATH);
    char *lastSlash = strrchr(exeDir, '\\');
    if (lastSlash) *(lastSlash + 1) = '\0';

    /* Build command: python\pythonw.exe -m mirance.main */
    snprintf(cmdLine, sizeof(cmdLine),
             "\"%spython\\pythonw.exe\" -m mirance.main", exeDir);

    /* Set working directory to app root */
    SetCurrentDirectoryA(exeDir);

    /* Launch Python (no console window) */
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        /* If pythonw.exe fails, try python.exe so user sees the error */
        snprintf(cmdLine, sizeof(cmdLine),
                 "\"%spython\\python.exe\" -m mirance.main", exeDir);
        CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi);
    }

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 0;
}
