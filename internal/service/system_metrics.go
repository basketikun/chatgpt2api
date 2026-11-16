package service

import (
	"context"
	"log"
	"os"
	"sync"
	"time"

	"github.com/shirou/gopsutil/v4/disk"
	"github.com/shirou/gopsutil/v4/mem"
	"github.com/shirou/gopsutil/v4/process"
)

type MemoryMetric struct {
	Total          uint64  `json:"total"`
	Used           uint64  `json:"used"`
	Available      uint64  `json:"available"`
	Percent        float64 `json:"percent"`
	Process        uint64  `json:"process"`
	ProcessPercent float64 `json:"process_percent"`
}

type DiskMetric struct {
	Path    string  `json:"path"`
	Total   uint64  `json:"total"`
	Used    uint64  `json:"used"`
	Free    uint64  `json:"free"`
	Percent float64 `json:"percent"`
}

type SystemOverview struct {
	SampledAt time.Time         `json:"sampled_at"`
	Memory    *MemoryMetric     `json:"memory"`
	Disk      *DiskMetric       `json:"disk"`
	Errors    map[string]string `json:"errors"`
}

var selfProcess = sync.OnceValues(func() (*process.Process, error) { return process.NewProcess(int32(os.Getpid())) })

func (s *OverviewService) System(ctx context.Context) *SystemOverview {
	s.systemMu.Lock()
	defer s.systemMu.Unlock()
	if s.system != nil && time.Since(s.system.SampledAt) < 5*time.Second {
		return s.system
	}
	result := &SystemOverview{Errors: map[string]string{}}
	self, err := selfProcess()
	if err != nil {
		result.Errors["process"] = "本进程数据读取失败: " + err.Error()
	}
	memory, err := mem.VirtualMemoryWithContext(ctx)
	if err != nil {
		result.Errors["memory"] = "内存数据读取失败: " + err.Error()
	} else {
		result.Memory = &MemoryMetric{Total: memory.Total, Used: memory.Used, Available: memory.Available, Percent: memory.UsedPercent}
		if self != nil {
			if info, err := self.MemoryInfoWithContext(ctx); err != nil {
				result.Errors["process"] = "本进程内存读取失败: " + err.Error()
			} else {
				result.Memory.Process = info.RSS
				result.Memory.ProcessPercent = float64(info.RSS) / float64(memory.Total) * 100
			}
		}
	}
	path, err := os.Getwd()
	if err != nil {
		result.Errors["disk"] = "运行目录读取失败: " + err.Error()
	} else {
		usage, err := disk.UsageWithContext(ctx, path)
		if err != nil {
			result.Errors["disk"] = "磁盘数据读取失败: " + err.Error()
		} else {
			result.Disk = &DiskMetric{Path: usage.Path, Total: usage.Total, Used: usage.Used, Free: usage.Free, Percent: usage.UsedPercent}
		}
	}
	for metric, detail := range result.Errors {
		log.Printf("system metrics %s: %s", metric, detail)
	}
	result.SampledAt = time.Now()
	s.system = result
	return result
}
