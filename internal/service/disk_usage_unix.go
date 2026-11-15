//go:build aix || darwin || dragonfly || freebsd || linux || netbsd || openbsd || solaris

package service

import "syscall"

func diskUsage(path string) (total uint64, free uint64, err error) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return 0, 0, err
	}
	return stat.Blocks * uint64(stat.Bsize), stat.Bavail * uint64(stat.Bsize), nil
}
