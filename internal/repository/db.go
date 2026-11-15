package repository

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/glebarez/sqlite"
	mysqlDriver "github.com/go-sql-driver/mysql"
	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var ErrNotFound = errors.New("not found")

type Repository struct{ db *gorm.DB }

func Open(databaseURL string) (*Repository, error) {
	var dialector gorm.Dialector
	switch {
	case strings.HasPrefix(databaseURL, "postgresql://"), strings.HasPrefix(databaseURL, "postgres://"):
		dialector = postgres.Open(databaseURL)
	case strings.HasPrefix(databaseURL, "mysql://"):
		dsn, err := mysqlDSN(databaseURL)
		if err != nil {
			return nil, err
		}
		dialector = mysql.Open(dsn)
	case strings.HasPrefix(databaseURL, "sqlite:///"):
		path := strings.TrimPrefix(databaseURL, "sqlite:///")
		if path != ":memory:" {
			if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
				return nil, err
			}
		}
		// 连接级 PRAGMA 必须写进连接串，保证连接池里每个连接都生效
		dialector = sqlite.Open(path + "?_pragma=busy_timeout(10000)&_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)")
	default:
		return nil, fmt.Errorf("不支持的数据库地址: %s", databaseURL)
	}
	db, err := gorm.Open(dialector)
	if err != nil {
		return nil, err
	}
	sqlDB, err := db.DB()
	if err != nil {
		return nil, err
	}
	sqlDB.SetConnMaxLifetime(time.Hour)
	if !strings.HasPrefix(databaseURL, "sqlite:///") {
		sqlDB.SetMaxOpenConns(50)
		sqlDB.SetMaxIdleConns(10)
	}
	models := []any{&Account{}, &APIKey{}, &Conversation{}, &File{}, &Log{}, &Task{}, &TaskResult{}, &CPA{}, &Sub{}}
	if db.Dialector.Name() == "sqlite" {
		err = migrateSQLite(db, models)
	} else {
		err = db.AutoMigrate(models...)
	}
	if err != nil {
		return nil, err
	}
	return &Repository{db: db}, nil
}

func migrateSQLite(db *gorm.DB, models []any) error {
	migrator := db.Migrator()
	for _, model := range models {
		if !migrator.HasTable(model) {
			if err := migrator.CreateTable(model); err != nil {
				return err
			}
			continue
		}
		statement := &gorm.Statement{DB: db}
		if err := statement.Parse(model); err != nil {
			return err
		}
		for _, field := range statement.Schema.Fields {
			if field.IgnoreMigration || field.DBName == "" || migrator.HasColumn(model, field.DBName) {
				continue
			}
			if err := migrator.AddColumn(model, field.Name); err != nil {
				return err
			}
		}
	}
	return nil
}

func mysqlDSN(databaseURL string) (string, error) {
	parsed, err := url.Parse(databaseURL)
	if err != nil {
		return "", err
	}
	password, _ := parsed.User.Password()
	config := mysqlDriver.Config{User: parsed.User.Username(), Passwd: password, Net: "tcp", Addr: parsed.Host, DBName: strings.TrimPrefix(parsed.Path, "/"), Params: map[string]string{}, ParseTime: true, Loc: time.UTC}
	for key, values := range parsed.Query() {
		if len(values) > 0 {
			config.Params[key] = values[len(values)-1]
		}
	}
	return config.FormatDSN(), nil
}

func (r *Repository) Close() error {
	db, err := r.db.DB()
	if err != nil {
		return err
	}
	return db.Close()
}
