"""Tests for SQLite database operations."""


class TestDatabase:
    def test_init_creates_tables(self, test_db):
        """init_db should be idempotent."""
        test_db.init_db()  # second call shouldn't fail

    def test_save_and_get_draft(self, test_db):
        draft_id = test_db.save_draft(
            title="Test Post",
            body="This is a test post body.",
            pillar="ai_engineering",
            format="hot_take",
            source_activity_ids=[1, 2, 3],
        )
        assert draft_id is not None

        draft = test_db.get_draft(draft_id)
        assert draft is not None
        assert draft["title"] == "Test Post"
        assert draft["pillar"] == "ai_engineering"
        assert draft["status"] == "pending"

    def test_list_drafts_all(self, test_db):
        test_db.save_draft("A", "body", "p1", "f1", [])
        test_db.save_draft("B", "body", "p2", "f2", [])
        drafts = test_db.list_drafts()
        assert len(drafts) == 2

    def test_list_drafts_by_status(self, test_db):
        id1 = test_db.save_draft("A", "body", "p1", "f1", [])
        test_db.save_draft("B", "body", "p2", "f2", [])
        test_db.update_draft(id1, status="approved")

        pending = test_db.list_drafts(status="pending")
        assert len(pending) == 1
        approved = test_db.list_drafts(status="approved")
        assert len(approved) == 1

    def test_update_draft(self, test_db):
        draft_id = test_db.save_draft("Old", "old body", "p", "f", [])
        test_db.update_draft(draft_id, title="New", body="new body")
        draft = test_db.get_draft(draft_id)
        assert draft["title"] == "New"
        assert draft["body"] == "new body"

    def test_get_nonexistent_draft(self, test_db):
        assert test_db.get_draft(9999) is None

    def test_save_activities(self, test_db):
        activities = [
            {
                "repo_full_name": "org/repo",
                "activity_type": "commit",
                "title": "fix: bug",
                "description": "Fixed a bug",
                "diff_summary": "+10 -5",
                "pillar": "ai_engineering",
                "content_score": 7.5,
            },
            {
                "repo_full_name": "org/repo2",
                "activity_type": "pull_request",
                "title": "feat: new thing",
                "description": "Added feature",
                "diff_summary": "+100 -20",
                "pillar": "data_architecture",
                "content_score": 8.0,
            },
        ]
        ids = test_db.save_activities(activities)
        assert len(ids) == 2

    def test_get_activities_since(self, test_db):
        test_db.save_activities([
            {
                "repo_full_name": "org/repo",
                "activity_type": "commit",
                "title": "test",
                "description": "desc",
                "diff_summary": "+1 -1",
                "pillar": "p",
                "content_score": 5.0,
            }
        ])
        # Activities just saved should be after 2020
        activities = test_db.get_activities_since("2020-01-01")
        assert len(activities) >= 1

    def test_get_last_scan_date(self, test_db):
        assert test_db.get_last_scan_date() is None
        test_db.save_activities([
            {
                "repo_full_name": "org/repo",
                "activity_type": "commit",
                "title": "t",
                "description": "d",
                "diff_summary": "s",
                "pillar": "p",
                "content_score": 1.0,
            }
        ])
        assert test_db.get_last_scan_date() is not None
