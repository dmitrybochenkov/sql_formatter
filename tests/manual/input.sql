SELECT 
	t.user_id				-- 4 пробела
	, t.user_name			-- ведущаая запятая
	, sub.total_amount
FROM prd_tables.users_v t	-- на одной строке с ФРОМ, если одна таблица. Если 2 - с новой строки каждая, ведущаая запятая 
							-- пустая строка перед джойнами
INNER JOIN (				-- перенос после скобки, вложенный запрос сдвинут
	SELECT
	    s.user_id
	    , SUM(s.purchase_amtz) AS total_amount	-- СУМ капсом
	FROM prd_tables.sales_v s

	WHERE 1=1									-- 1=1 добавляется если несколько АНД. в ВХЕРЕ 1 условие - на этой же строке 
		AND s.status_cd = 'COMPLETED'
		AND s.purchase_date >= '2026-01-01'

	GROUP BY 									-- если более 1 - с новой строки и с ентерами
		1,
		2
) sub 
ON t.user_id = sub.user_id				--	с новой строки под джойнами
	AND sub.cond1 = 1					-- отступы
	AND sub.cond2 = 2
							-- пустая строка после джойнов

WHERE 1=1
    AND t.country_code = 'RU'
    AND t.is_active = 1
;				-- на новой строке на уровне запроса