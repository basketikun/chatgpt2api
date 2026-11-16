//go:build windows

package service

import (
	"syscall"

	"golang.org/x/sys/windows"
)

func diskUsage(path string) (total uint64, free uint64, err error) {
	directory, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return 0, 0, err
	}
	var available, totalBytes, freeBytes uint64
	if err := windows.GetDiskFreeSpaceEx(directory, &available, &totalBytes, &freeBytes); err != nil {
		return 0, 0, err
	}
	return totalBytes, freeBytes, nil
}
