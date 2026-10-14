# 明细上传样例

detail_local.csv 为本网、detail_other.csv 为异网。数据全部为明确标记的虚构标识，不是真实用户；请按相同英文列名适配正式文件。一个文件只含一个网别，允许多个月账期，已有任何记录的月份整批拒绝（模拟数据也算已有记录）。
XLSX 可将相同内容保存为 Excel 文件，只保留一个工作表，month_id、device_number、uid 设为文本。公共列全部保留，本网保留 uid 列，异网不含 uid 列；cell_name、street_name、uid 可空。
实际导入均标记 is_demo=false；样例仅用于文件格式展示，不代表生产用户。
