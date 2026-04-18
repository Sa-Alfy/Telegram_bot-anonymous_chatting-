"""
Tests for database/repositories/: UserRepository, AdminRepository, ReportRepository,
FriendRepository, RevealRepository, SessionRepository, StatsRepository
All tests mock the global 'db' instance.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ═══════════════════════════════════════════════════════
# 1. UserRepository Tests
# ═══════════════════════════════════════════════════════
class TestUserRepository:
    @pytest.mark.asyncio
    async def test_get_by_telegram_id_none(self):
        from database.repositories.user_repository import UserRepository
        with patch("database.repositories.user_repository.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value=None)
            result = await UserRepository.get_by_telegram_id(12345)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_success(self):
        from database.repositories.user_repository import UserRepository
        mock_row = {
            "telegram_id": 12345,
            "coins": 50,
            "xp": 100,
            "level": 2,
            "gender": "Male",
            "json_data": '{"extra_field": "val"}'
        }
        with patch("database.repositories.user_repository.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value=mock_row)
            result = await UserRepository.get_by_telegram_id(12345)
            assert result is not None
            assert result["coins"] == 50
            assert result["extra_field"] == "val"

    @pytest.mark.asyncio
    async def test_create_user(self):
        from database.repositories.user_repository import UserRepository
        with patch("database.repositories.user_repository.db") as mock_db:
            mock_db.execute = AsyncMock()
            # Mock get_by_telegram_id to return something after creation
            with patch.object(UserRepository, "get_by_telegram_id", AsyncMock(return_value={"id": 1})):
                result = await UserRepository.create(123, "user", "Alice")
                assert result == {"id": 1}
                mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user(self):
        from database.repositories.user_repository import UserRepository
        with patch("database.repositories.user_repository.db") as mock_db:
            mock_db.execute = AsyncMock()
            result = await UserRepository.update(123, coins=60, level=3)
            assert result is True
            mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_coins(self):
        from database.repositories.user_repository import UserRepository
        with patch("database.repositories.user_repository.db") as mock_db:
            mock_db.execute = AsyncMock()
            await UserRepository.increment_coins(123, 10)
            mock_db.execute.assert_called_once()


# ═══════════════════════════════════════════════════════
# 2. AdminRepository Tests
# ═══════════════════════════════════════════════════════
class TestAdminRepository:
    @pytest.mark.asyncio
    async def test_get_system_stats(self):
        from database.repositories.admin_repository import AdminRepository
        # get_system_stats calls fetchone 3 times, each expecting {"count": N}
        count_row = {"count": 100}
        with patch("database.repositories.admin_repository.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value=count_row)
            result = await AdminRepository.get_system_stats()
            assert result["total_users"] == 100

    @pytest.mark.asyncio
    async def test_get_blocked_users(self):
        from database.repositories.admin_repository import AdminRepository
        with patch("database.repositories.admin_repository.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=[{"telegram_id": 1}])
            result = await AdminRepository.get_banned_users()
            assert len(result) == 1


# ═══════════════════════════════════════════════════════
# 3. ReportRepository Tests
# ═══════════════════════════════════════════════════════
class TestReportRepository:
    @pytest.mark.asyncio
    async def test_create_report(self):
        from database.repositories.report_repository import ReportRepository
        with patch("database.repositories.report_repository.db") as mock_db:
            # create() uses fetchval (RETURNING clause)
            mock_db.fetchval = AsyncMock(return_value=1)
            result = await ReportRepository.create(1, 2, "Harassment")
            assert result == 1
            mock_db.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pending_appeals(self):
        from database.repositories.report_repository import ReportRepository
        with patch("database.repositories.report_repository.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=[])
            result = await ReportRepository.get_pending_appeals()
            assert result == []


# ═══════════════════════════════════════════════════════
# 4. FriendRepository Tests
# ═══════════════════════════════════════════════════════
class TestFriendRepository:
    @pytest.mark.asyncio
    async def test_add_friend_request(self):
        from database.repositories.friend_repository import FriendRepository
        with patch("database.repositories.friend_repository.db") as mock_db:
            # send_request first calls fetchone to check for existing (returns None)
            # then calls execute to insert
            mock_db.fetchone = AsyncMock(return_value=None)
            mock_db.execute = AsyncMock()
            result = await FriendRepository.send_request(1, 2)
            assert result is True

    @pytest.mark.asyncio
    async def test_get_friends(self):
        from database.repositories.friend_repository import FriendRepository
        with patch("database.repositories.friend_repository.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=[])
            result = await FriendRepository.get_friends_list(1)
            assert result == []


# ═══════════════════════════════════════════════════════
# 5. SessionRepository Tests
# ═══════════════════════════════════════════════════════
class TestSessionRepository:
    @pytest.mark.asyncio
    async def test_create_session(self):
        from database.repositories.session_repository import SessionRepository
        with patch("database.repositories.session_repository.db") as mock_db:
            mock_db.fetchval = AsyncMock(return_value=1)
            result = await SessionRepository.create(1, 2)
            assert result == 1

    @pytest.mark.asyncio
    async def test_end_session(self):
        from database.repositories.session_repository import SessionRepository
        with patch("database.repositories.session_repository.db") as mock_db:
            mock_db.execute = AsyncMock()
            await SessionRepository.end_session(1, 60, 5, 5, 10, 10)
            mock_db.execute.assert_called_once()
