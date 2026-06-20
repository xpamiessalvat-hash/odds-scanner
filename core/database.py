import os

import psycopg


DATABASE_URL = os.getenv(
    "DATABASE_URL"
)


def get_connection():

    return psycopg.connect(
        DATABASE_URL
    )


def create_tables():

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute("""

            CREATE TABLE IF NOT EXISTS opportunities (

                id TEXT PRIMARY KEY,

                created_at TIMESTAMP,

                league TEXT,

                match TEXT,

                market TEXT,

                designation TEXT,

                points TEXT,

                steam_level TEXT,

                movement_pct REAL,

                pinnacle_old INTEGER,

                pinnacle_new INTEGER,

                game_time TIMESTAMP,

                bet365_odd INTEGER,

                edge REAL,

                status TEXT

            );

            """)

        conn.commit()


def save_candidate(candidate):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO opportunities (
                    id,
                    created_at,
                    league,
                    match,
                    market,
                    designation,
                    points,
                    steam_level,
                    movement_pct,
                    pinnacle_old,
                    pinnacle_new,
                    game_time,
                    bet365_odd,
                    edge,
                    status
                )
                VALUES (
                    %(id)s,
                    %(timestamp)s,
                    %(league)s,
                    %(match)s,
                    %(market)s,
                    %(designation)s,
                    %(points)s,
                    %(steam_level)s,
                    %(movement_pct)s,
                    %(pinnacle_old)s,
                    %(pinnacle_new)s,
                    %(game_time)s,
                    %(bet365_odd)s,
                    %(edge)s,
                    %(status)s
                );
                """,
                candidate
            )

        conn.commit()