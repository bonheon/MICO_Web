import sqlite3
import pandas as pd


class MergeData:

    @staticmethod
    def get_merge_data(lot_code, oper_desc, fab):
        # 사내 DB에서 (lot_code, oper_desc, fab) 기준 merge 테이블 조회
        # 테이블명 예: {lot_code}_{oper_desc}_{fab}
        # TODO: 사내 DB 연결로 교체
        merge_df = pd.DataFrame()
        return merge_df


class GetData:

    @staticmethod
    def get_detail_info(family=None, product_list=None, oper_desc=None, fab=None):
        DB_PATH = '../db.sqlite3'
        conn = sqlite3.connect(DB_PATH)

        detail_df = pd.read_sql_query("""
        SELECT
            c.family,
            c.product   AS lot_code,
            c.oper_id,
            c.oper_desc,
            s.fab,
            s.device,
            s.recipe_id,
            s.maker,
            d.*
        FROM setup_mico_detail      AS d
        JOIN setup_mico_subcategory AS s ON d.subcategory_id = s.id
        JOIN setup_mico_category    AS c ON s.category_id   = c.id
        ORDER BY c.product, c.oper_id, s.fab, s.device, s.recipe_id
        """, conn)
        conn.close()

        if family:
            detail_df = detail_df[detail_df['family'] == family]
        if product_list:
            detail_df = detail_df[detail_df['lot_code'].isin(product_list)]
        if oper_desc:
            detail_df = detail_df[detail_df['oper_desc'] == oper_desc]
        if fab:
            detail_df = detail_df[detail_df['fab'] == fab]

        print(f'Set-up 조회: {len(detail_df)}건 '
              f'(family={family}, product_list={product_list}, oper_desc={oper_desc}, fab={fab})')
        return detail_df

    @staticmethod
    def get_recipe_groups(lot_code, oper_desc, fab):
        # web DB의 RecipeGroup 조회
        # RecipeGroup → Category(lot_code, oper_desc) + SubCategory(fab, recipe_id)
        # 반환: [SimpleNamespace(recipe_ids=[...]), ...]  또는 빈 리스트
        # TODO: DB 연결로 교체
        query = """
        SELECT
            rg.id           AS group_id,
            rg.name         AS group_name,
            s.recipe_id
        FROM setup_mico_recipegroup             AS rg
        JOIN setup_mico_recipegroup_subcategories AS rs ON rg.id = rs.recipegroup_id
        JOIN setup_mico_subcategory               AS s  ON rs.subcategory_id = s.id
        JOIN setup_mico_category                  AS c  ON rg.category_id = c.id
        WHERE c.product  = '{lot_code}'
          AND c.oper_desc = '{oper_desc}'
          AND s.fab       = '{fab}'
        """.format(lot_code=lot_code, oper_desc=oper_desc, fab=fab)

        DB_PATH = '../db.sqlite3'
        conn = sqlite3.connect(DB_PATH)
        rg_df = pd.read_sql_query(query, conn)
        conn.close()

        if rg_df.empty:
            return []

        from types import SimpleNamespace
        groups = []
        for _, grp in rg_df.groupby('group_id'):
            groups.append(SimpleNamespace(
                group_id=grp['group_id'].iloc[0],
                group_name=grp['group_name'].iloc[0],
                recipe_ids=grp['recipe_id'].tolist(),
            ))
        return groups
