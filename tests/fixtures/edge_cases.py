"""Existing synthetic SQL inputs and expected outputs; preserved verbatim."""
import textwrap

def sql(source):
    return textwrap.dedent(source).strip("\n") + "\n"

GOLDEN = {
    "right_comment_followed_by_comma": (
        "SELECT id, -- identifier\n name, amount -- final field\nFROM payments;",
        sql("""\
        SELECT
            id -- identifier
            , name
            , amount -- final field
        FROM payments
        ;"""),
    ),
    "comment_above_first_field": (
        "SELECT\n-- identifier\nid FROM users;",
        sql("""\
        SELECT
            -- identifier
            id
        FROM users
        ;"""),
    ),
    "consecutive_comment_lines": (
        "SELECT id,\n-- first\n-- second\nname FROM users;",
        sql("""\
        SELECT
            id
            -- first
            -- second
            , name
        FROM users
        ;"""),
    ),
    "comment_above_join": (
        "SELECT u.id FROM users u\n\n-- payments\nINNER JOIN payments p ON p.user_id=u.id;",
        sql("""\
        SELECT
            u.id
        FROM users u

        -- payments
        INNER JOIN payments p
        ON p.user_id = u.id
        ;"""),
    ),
    "nested_cte_select_from_no_blank": (
        "WITH c AS (SELECT user_id, amount FROM payments) SELECT user_id FROM c;",
        sql("""\
        WITH c AS (
            SELECT
                user_id
                , amount
            FROM payments
        )

        SELECT
            user_id
        FROM c
        ;"""),
    ),
    "join_and_conditions_no_synthetic_true": (
        "SELECT u.id FROM users u JOIN sales s ON u.id=s.user_id AND s.status='OK';",
        sql("""\
        SELECT
            u.id
        FROM users u

        JOIN sales s
        ON u.id = s.user_id
            AND s.status = 'OK'
        ;"""),
    ),
    "where_between_and_is_not_split": (
        "SELECT id FROM t WHERE x BETWEEN 1 AND 5;",
        sql("""\
        SELECT
            id
        FROM t

        WHERE x BETWEEN 1 AND 5
        ;"""),
    ),
    "qualify_two_conditions_no_synthetic_true": (
        "SELECT id FROM t QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts)=1 AND amount>0;",
        sql("""\
        SELECT
            id
        FROM t

        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY id
            ORDER BY ts
        ) = 1
            AND amount > 0
        ;"""),
    ),
    "set_operator_blank_lines": (
        "SELECT id FROM a INTERSECT SELECT id FROM b;",
        sql("""\
        SELECT
            id
        FROM a

        INTERSECT

        SELECT
            id
        FROM b
        ;"""),
    ),
    "literal_whitespace_unchanged": (
        "SELECT 'a  b' AS txt FROM t;",
        sql("""\
        SELECT
            'a  b' AS txt
        FROM t
        ;"""),
    ),
}
