"""
E2E tests for S3 Destination API endpoints.

Tests the full S3 destination configuration flow including:
- Feature flag validation
- Connection testing
- Configuration creation/update
- Status retrieval
- Configuration deletion

These tests require S3_DESTINATION feature flag to be enabled for the test organization.
"""

import pytest
import httpx


class TestS3DestinationAPI:
    """Test suite for S3 Destination API endpoints."""

    @pytest.mark.asyncio
    async def test_get_s3_status_feature_disabled(self, api_client: httpx.AsyncClient):
        """Test S3 status endpoint when feature flag is disabled (default state)."""
        response = await api_client.get("/s3/status")

        assert response.status_code == 200, f"Failed to get S3 status: {response.text}"

        status = response.json()
        assert "feature_enabled" in status
        assert "configured" in status

        # Most test orgs won't have S3_DESTINATION feature enabled
        if not status["feature_enabled"]:
            assert status["configured"] is False
            assert "not enabled" in status["message"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.getoption('--s3-enabled', False)",
        reason="S3_DESTINATION feature flag not enabled for test org",
    )
    async def test_s3_connection_test_invalid_role(self, api_client: httpx.AsyncClient):
        """Test S3 connection test with invalid IAM role ARN.

        Skipped unless --s3-enabled flag is provided and feature is enabled.
        """
        invalid_config = {
            "role_arn": "arn:aws:iam::999999999999:role/non-existent-role",
            "external_id": "test-external-id-12345",
            "bucket_name": "non-existent-bucket",
            "bucket_prefix": "airweave/",
            "aws_region": "us-east-1",
        }

        response = await api_client.post("/s3/test", json=invalid_config)

        # Should fail with 400 Bad Request (connection test failed)
        assert response.status_code in [400, 403], f"Unexpected response: {response.text}"

        if response.status_code == 400:
            error = response.json()
            assert "detail" in error
            assert any(
                keyword in error["detail"].lower()
                for keyword in ["failed", "access", "assume", "denied"]
            )

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.getoption('--s3-enabled', False)",
        reason="S3_DESTINATION feature flag not enabled for test org",
    )
    async def test_s3_configure_missing_fields(self, api_client: httpx.AsyncClient):
        """Test S3 configuration with missing required fields."""
        incomplete_config = {
            "role_arn": "arn:aws:iam::123456789012:role/airweave-writer",
            # Missing external_id and bucket_name
        }

        response = await api_client.post("/s3/configure", json=incomplete_config)

        # Should fail with 422 Validation Error
        assert response.status_code == 422, f"Expected validation error: {response.text}"

        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.getoption('--s3-enabled', False)",
        reason="S3_DESTINATION feature flag not enabled for test org",
    )
    async def test_s3_configure_invalid_arn_format(self, api_client: httpx.AsyncClient):
        """Test S3 configuration with invalid ARN format."""
        invalid_config = {
            "role_arn": "not-a-valid-arn",
            "external_id": "test-external-id",
            "bucket_name": "test-bucket",
            "bucket_prefix": "airweave/",
            "aws_region": "us-east-1",
        }

        response = await api_client.post("/s3/configure", json=invalid_config)

        # Should fail with either 400 (connection test) or 422 (validation)
        assert response.status_code in [400, 422], f"Expected error response: {response.text}"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.getoption('--s3-enabled', False)",
        reason="S3_DESTINATION feature flag not enabled for test org",
    )
    async def test_delete_s3_configuration_not_found(self, api_client: httpx.AsyncClient):
        """Test deleting S3 configuration when none exists."""
        # First ensure no configuration exists by trying to get status
        status_response = await api_client.get("/s3/status")
        status = status_response.json()

        if not status.get("configured", False):
            # Try to delete non-existent configuration
            response = await api_client.delete("/s3/configure")

            # Should return 404 Not Found
            assert response.status_code == 404, f"Unexpected response: {response.text}"

            error = response.json()
            assert "detail" in error
            assert "not found" in error["detail"].lower()

    @pytest.mark.asyncio
    async def test_s3_endpoints_return_json(self, api_client: httpx.AsyncClient):
        """Test that all S3 endpoints return valid JSON."""
        # GET /s3/status should always work
        response = await api_client.get("/s3/status")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

        # Parse JSON successfully
        status = response.json()
        assert isinstance(status, dict)

    @pytest.mark.asyncio
    async def test_s3_status_response_structure(self, api_client: httpx.AsyncClient):
        """Test that S3 status endpoint returns expected structure."""
        response = await api_client.get("/s3/status")
        assert response.status_code == 200

        status = response.json()

        # Required fields in all cases
        assert "feature_enabled" in status
        assert "configured" in status
        assert isinstance(status["feature_enabled"], bool)
        assert isinstance(status["configured"], bool)

        # If feature is enabled and configured, should have additional fields
        if status.get("configured"):
            assert "connection_id" in status
            assert "bucket_name" in status
            assert "role_arn" in status
            assert "status" in status
            # Verify ARN format if present
            if status.get("role_arn"):
                assert status["role_arn"].startswith("arn:aws:iam::")


class TestS3DestinationFullFlow:
    """
    Full flow integration tests for S3 destination.

    These tests should only run when S3_DESTINATION feature is enabled
    and valid AWS credentials are available.
    """

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.getoption('--s3-full-flow', False)",
        reason="Full S3 flow test requires valid AWS credentials",
    )
    async def test_full_s3_configuration_lifecycle(self, api_client: httpx.AsyncClient):
        """
        Test complete S3 destination lifecycle:
        1. Check initial status (not configured)
        2. Test connection
        3. Configure S3 destination
        4. Verify status (configured)
        5. Update configuration
        6. Delete configuration
        7. Verify status (not configured)

        Requires:
        - S3_DESTINATION feature flag enabled
        - Valid test AWS role ARN in environment
        - TEST_S3_ROLE_ARN, TEST_S3_EXTERNAL_ID, TEST_S3_BUCKET_NAME env vars
        """
        import os

        # Get test credentials from environment
        test_role_arn = os.getenv("TEST_S3_ROLE_ARN")
        test_external_id = os.getenv("TEST_S3_EXTERNAL_ID")
        test_bucket_name = os.getenv("TEST_S3_BUCKET_NAME")

        if not all([test_role_arn, test_external_id, test_bucket_name]):
            pytest.skip(
                "TEST_S3_ROLE_ARN, TEST_S3_EXTERNAL_ID, and TEST_S3_BUCKET_NAME "
                "must be set for full flow test"
            )

        test_config = {
            "role_arn": test_role_arn,
            "external_id": test_external_id,
            "bucket_name": test_bucket_name,
            "bucket_prefix": "test-airweave/",
            "aws_region": "us-east-1",
        }

        # Step 1: Check initial status
        status_response = await api_client.get("/s3/status")
        assert status_response.status_code == 200
        initial_status = status_response.json()
        assert initial_status["feature_enabled"], "S3_DESTINATION feature must be enabled"

        # Step 2: Test connection
        test_response = await api_client.post("/s3/test", json=test_config)
        assert test_response.status_code == 200, f"Connection test failed: {test_response.text}"
        test_result = test_response.json()
        assert test_result["status"] == "success"

        # Step 3: Configure S3 destination
        configure_response = await api_client.post("/s3/configure", json=test_config)
        assert (
            configure_response.status_code == 200
        ), f"Configuration failed: {configure_response.text}"
        configure_result = configure_response.json()
        assert configure_result["status"] in ["created", "updated"]
        connection_id = configure_result["connection_id"]

        # Step 4: Verify configured status
        status_response = await api_client.get("/s3/status")
        assert status_response.status_code == 200
        configured_status = status_response.json()
        assert configured_status["configured"] is True
        assert configured_status["bucket_name"] == test_bucket_name
        assert configured_status["role_arn"] == test_role_arn
        assert configured_status["connection_id"] == connection_id

        # Step 5: Update configuration (change prefix)
        updated_config = test_config.copy()
        updated_config["bucket_prefix"] = "updated-airweave/"
        update_response = await api_client.post("/s3/configure", json=updated_config)
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        update_result = update_response.json()
        assert update_result["status"] == "updated"

        # Step 6: Delete configuration
        delete_response = await api_client.delete("/s3/configure")
        assert delete_response.status_code == 200, f"Deletion failed: {delete_response.text}"
        delete_result = delete_response.json()
        assert delete_result["status"] == "success"

        # Step 7: Verify not configured
        final_status_response = await api_client.get("/s3/status")
        assert final_status_response.status_code == 200
        final_status = final_status_response.json()
        assert final_status["configured"] is False
