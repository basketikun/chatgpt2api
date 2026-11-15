package service

import (
	"context"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
)

type ConversationService struct{ repo *repository.Repository }

func NewConversationService(repo *repository.Repository) *ConversationService {
	return &ConversationService{repo: repo}
}
func (s *ConversationService) List(ctx context.Context, ownerID string, conversationType string) ([]repository.Conversation, error) {
	return s.repo.Conversations(ctx, ownerID, conversationType)
}
func (s *ConversationService) Get(ctx context.Context, ownerID string, id int64) (repository.Conversation, error) {
	return s.repo.Conversation(ctx, ownerID, id)
}
func (s *ConversationService) Create(ctx context.Context, item repository.Conversation) (repository.Conversation, error) {
	if item.Messages == nil {
		item.Messages = []map[string]any{}
	}
	if item.Extra == nil {
		item.Extra = map[string]any{}
	}
	now := time.Now().UTC()
	item.CreatedAt, item.UpdatedAt = now, now
	return s.repo.SaveConversation(ctx, item)
}

func (s *ConversationService) Update(ctx context.Context, ownerID string, id int64, patch ConversationPatch) (repository.Conversation, error) {
	item, err := s.repo.Conversation(ctx, ownerID, id)
	if err != nil {
		return repository.Conversation{}, err
	}
	if patch.Title != nil {
		item.Title = *patch.Title
	}
	if patch.Type != nil {
		item.Type = *patch.Type
	}
	if patch.Model != nil {
		item.Model = *patch.Model
	}
	if patch.Messages != nil {
		item.Messages = patch.Messages
	}
	if patch.Extra != nil {
		item.Extra = patch.Extra
	}
	item.UpdatedAt = time.Now().UTC()
	return s.repo.SaveConversation(ctx, item)
}

func (s *ConversationService) Delete(ctx context.Context, ownerID string, id int64) (bool, error) {
	return s.repo.DeleteConversation(ctx, ownerID, id)
}
func (s *ConversationService) Clear(ctx context.Context, ownerID string, conversationType string) (int64, error) {
	return s.repo.DeleteConversations(ctx, ownerID, conversationType)
}

type ConversationPatch struct {
	Title    *string
	Type     *string
	Model    *string
	Messages any
	Extra    map[string]any
}
