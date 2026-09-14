-- users, profiles and access_tokens as they stand at revision a7e4c91d20b8.
-- Copied from sqlite_master of a backup of the production database migrated
-- to that revision; only trailing whitespace was stripped.

CREATE TABLE users (
	id CHAR(36) NOT NULL,
	external_id VARCHAR(50) NOT NULL,
	email VARCHAR(320) NOT NULL,
	hashed_password VARCHAR(1024) NOT NULL,
	is_active BOOLEAN DEFAULT 1 NOT NULL,
	is_superuser BOOLEAN DEFAULT 0 NOT NULL,
	is_verified BOOLEAN DEFAULT 0 NOT NULL,
	role VARCHAR(20) DEFAULT 'member' NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	deleted_at DATETIME,
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_deleted_at ON users (deleted_at);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE UNIQUE INDEX ix_users_external_id ON users (external_id);

CREATE INDEX ix_users_role ON users (role);

CREATE TABLE "profiles" (
	id CHAR(36) NOT NULL,
	external_id VARCHAR(50) NOT NULL,
	user_id CHAR(36) NOT NULL,
	name VARCHAR(50) NOT NULL,
	avatar_url VARCHAR(500),
	is_kids BOOLEAN DEFAULT 0 NOT NULL,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	deleted_at DATETIME,
	allowed_library_ids TEXT DEFAULT '[]' NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_profiles_deleted_at ON profiles (deleted_at);

CREATE UNIQUE INDEX ix_profiles_external_id ON profiles (external_id);

CREATE INDEX ix_profiles_user_id ON profiles (user_id);

CREATE TABLE access_tokens (
	token VARCHAR(43) NOT NULL,
	user_id CHAR(36) NOT NULL,
	current_profile_id CHAR(36),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (token),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(current_profile_id) REFERENCES profiles (id) ON DELETE SET NULL
);

CREATE INDEX ix_access_tokens_created_at ON access_tokens (created_at);

CREATE INDEX ix_access_tokens_user_id ON access_tokens (user_id);
