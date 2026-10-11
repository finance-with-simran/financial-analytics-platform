CREATE DATABASE IF NOT EXISTS finance_platform;
USE finance_platform;
CREATE TABLE `dim_companies` (
  `company_id` int NOT NULL AUTO_INCREMENT,
  `ticker` varchar(10) NOT NULL,
  `company_name` varchar(100) NOT NULL,
  `sector` varchar(50) DEFAULT NULL,
  `exchange` varchar(20) DEFAULT NULL,
  `currency` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`company_id`),
  UNIQUE KEY `ticker` (`ticker`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `fact_prices` (
  `price_id` int NOT NULL AUTO_INCREMENT,
  `company_id` int NOT NULL,
  `trade_date` date NOT NULL,
  `open_price` decimal(12,2) DEFAULT NULL,
  `high_price` decimal(12,2) DEFAULT NULL,
  `low_price` decimal(12,2) DEFAULT NULL,
  `close_price` decimal(12,2) DEFAULT NULL,
  `adj_close_price` decimal(12,2) DEFAULT NULL,
  `volume` bigint DEFAULT NULL,
  PRIMARY KEY (`price_id`),
  UNIQUE KEY `uq_company_date` (`company_id`,`trade_date`),
  CONSTRAINT `fact_prices_ibfk_1` FOREIGN KEY (`company_id`) REFERENCES `dim_companies` (`company_id`)
) ENGINE=InnoDB AUTO_INCREMENT=12160 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `fact_fundamentals` (
  `fund_id` int NOT NULL AUTO_INCREMENT,
  `company_id` int NOT NULL,
  `fiscal_year` year NOT NULL,
  `revenue` decimal(18,2) DEFAULT NULL,
  `net_income` decimal(18,2) DEFAULT NULL,
  `free_cash_flow` decimal(18,2) DEFAULT NULL,
  `total_debt` decimal(18,2) DEFAULT NULL,
  `cash_and_equivalents` decimal(18,2) DEFAULT NULL,
  `shares_outstanding` decimal(18,3) DEFAULT NULL,
  PRIMARY KEY (`fund_id`),
  UNIQUE KEY `uq_company_year` (`company_id`,`fiscal_year`),
  CONSTRAINT `fact_fundamentals_ibfk_1` FOREIGN KEY (`company_id`) REFERENCES `dim_companies` (`company_id`)
) ENGINE=InnoDB AUTO_INCREMENT=46 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
