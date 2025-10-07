"""migrate_github_repo_name_from_auth_to_config

Revision ID: 6e39730bc45b
Revises: c60291fb2129
Create Date: 2025-09-28 22:12:53.758477

"""

import json
from typing import Optional

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "6e39730bc45b"
down_revision = "c60291fb2129"
branch_labels = None
depends_on = None


def get_fernet() -> Fernet:
    """Get Fernet instance for encryption/decryption.
    
    Returns:
        Fernet instance configured with the encryption key.
        
    Raises:
        RuntimeError: If ENCRYPTION_KEY is not set.
    """
    import os
    
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY environment variable must be set")
    return Fernet(key.encode())


def encrypt_credentials(data: dict) -> str:
    """Encrypt credentials dictionary.
    
    Args:
        data: Dictionary containing credentials.
        
    Returns:
        Base64 encoded encrypted string.
    """
    f = get_fernet()
    json_str = json.dumps(data)
    encrypted = f.encrypt(json_str.encode())
    return encrypted.decode()


def decrypt_credentials(encrypted_str: str) -> Optional[dict]:
    """Decrypt credentials string.
    
    Args:
        encrypted_str: Base64 encoded encrypted string.
        
    Returns:
        Decrypted dictionary or None if decryption fails.
    """
    if not encrypted_str:
        return None
    
    try:
        f = get_fernet()
        decrypted = f.decrypt(encrypted_str.encode())
        return json.loads(decrypted.decode())
    except Exception:
        # Log but don't fail migration for individual record issues
        return None


def upgrade():
    """Move repo_name from encrypted GitHub credentials to source_connection config_fields.
    
    This migration handles the architectural change where repo_name is moved from
    GitHubAuthConfig (stored encrypted) to GitHubConfig (stored as plain config).
    """
    # Verify encryption key is available
    try:
        get_fernet()
    except RuntimeError as e:
        raise RuntimeError(str(e))
    
    conn = op.get_bind()
    
    # Query GitHub source connections with their credentials
    query = text("""
        SELECT 
            sc.id as source_connection_id,
            sc.config_fields,
            ic.id as credential_id,
            ic.encrypted_credentials
        FROM source_connection sc
        JOIN connection c ON sc.connection_id = c.id
        JOIN integration_credential ic ON c.integration_credential_id = ic.id
        WHERE sc.short_name = 'github'
        AND ic.encrypted_credentials IS NOT NULL
    """)
    
    result = conn.execute(query)
    rows = result.fetchall()
    
    migrated_count = 0
    skipped_count = 0
    
    for row in rows:
        # Decrypt credentials to check for repo_name
        credentials = decrypt_credentials(row.encrypted_credentials)
        if not credentials or "repo_name" not in credentials:
            skipped_count += 1
            continue
        
        repo_name = credentials.get("repo_name")
        if not repo_name:
            skipped_count += 1
            continue
        
        # Parse existing config_fields
        config_fields = {}
        if row.config_fields:
            if isinstance(row.config_fields, str):
                try:
                    config_fields = json.loads(row.config_fields)
                except json.JSONDecodeError:
                    config_fields = {}
            else:
                config_fields = dict(row.config_fields)
        
        # Skip if repo_name already exists in config
        if config_fields.get("repo_name"):
            skipped_count += 1
            continue
        
        # Add repo_name to config_fields
        config_fields["repo_name"] = repo_name
        
        # Remove repo_name from credentials
        del credentials["repo_name"]
        new_encrypted = encrypt_credentials(credentials)
        
        # Update source_connection config_fields
        update_sc = text("""
            UPDATE source_connection 
            SET config_fields = :config_fields,
                modified_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """)
        conn.execute(
            update_sc,
            {"config_fields": json.dumps(config_fields), "id": row.source_connection_id},
        )
        
        # Update integration_credential without repo_name
        update_ic = text("""
            UPDATE integration_credential 
            SET encrypted_credentials = :encrypted,
                modified_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """)
        conn.execute(
            update_ic,
            {"encrypted": new_encrypted, "id": row.credential_id},
        )
        
        migrated_count += 1
    
    print(f"✅ Migrated {migrated_count} GitHub connections")
    if skipped_count > 0:
        print(f"ℹ️  Skipped {skipped_count} connections (no repo_name or already migrated)")


def downgrade():
    """Move repo_name from source_connection config_fields back to encrypted credentials.
    
    This reverses the migration by moving repo_name back to the encrypted credentials.
    """
    # Verify encryption key is available
    try:
        get_fernet()
    except RuntimeError as e:
        raise RuntimeError(str(e))
    
    conn = op.get_bind()
    
    # Query GitHub source connections with repo_name in config_fields
    query = text("""
        SELECT 
            sc.id as source_connection_id,
            sc.config_fields,
            ic.id as credential_id,
            ic.encrypted_credentials
        FROM source_connection sc
        JOIN connection c ON sc.connection_id = c.id
        JOIN integration_credential ic ON c.integration_credential_id = ic.id
        WHERE sc.short_name = 'github'
        AND sc.config_fields IS NOT NULL
        AND sc.config_fields::jsonb ? 'repo_name'
    """)
    
    result = conn.execute(query)
    rows = result.fetchall()
    
    reverted_count = 0
    
    for row in rows:
        # Parse config_fields
        config_fields = {}
        if isinstance(row.config_fields, str):
            try:
                config_fields = json.loads(row.config_fields)
            except json.JSONDecodeError:
                continue
        else:
            config_fields = dict(row.config_fields)
        
        repo_name = config_fields.get("repo_name")
        if not repo_name:
            continue
        
        # Decrypt existing credentials or start fresh
        credentials = decrypt_credentials(row.encrypted_credentials) if row.encrypted_credentials else {}
        if credentials is None:
            credentials = {}
        
        # Add repo_name to credentials
        credentials["repo_name"] = repo_name
        new_encrypted = encrypt_credentials(credentials)
        
        # Remove repo_name from config_fields
        del config_fields["repo_name"]
        
        # Update source_connection - set to NULL if config_fields is empty
        if config_fields:
            update_sc = text("""
                UPDATE source_connection 
                SET config_fields = :config_fields,
                    modified_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """)
            conn.execute(
                update_sc,
                {"config_fields": json.dumps(config_fields), "id": row.source_connection_id},
            )
        else:
            update_sc = text("""
                UPDATE source_connection 
                SET config_fields = NULL,
                    modified_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """)
            conn.execute(update_sc, {"id": row.source_connection_id})
        
        # Update integration_credential with repo_name
        update_ic = text("""
            UPDATE integration_credential 
            SET encrypted_credentials = :encrypted,
                modified_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """)
        conn.execute(
            update_ic,
            {"encrypted": new_encrypted, "id": row.credential_id},
        )
        
        reverted_count += 1
    
    print(f"✅ Reverted {reverted_count} GitHub connections")