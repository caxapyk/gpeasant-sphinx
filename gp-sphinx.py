import argparse
import mariadb
import os
import textwrap
import shutil
import sys
import time

pj = os.path.join


class GPeasantSphinx(object):
    """Pull data from gpeasant database and generate corresponding
    reStructuredText files into a Sphinx source path using templates.
    """

    def __init__(
            self, db_user, db_user_passwd, db_host, db_port, db_database):
        super(GPeasantSphinx, self).__init__()

        # Connect to MariaDB Platform
        try:
            conn = mariadb.connect(
                user=db_user,
                password=db_user_passwd,
                host=db_host,
                port=db_port,
                database=db_database
            )

        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            sys.exit(1)

        self.cur = conn.cursor()

        self.root_dir = os.path.join(
            os.path.abspath(os.getcwd()), 'gp', 'pages')

        self.root_title = 'Административно-территориальное деление'
        self.undefined_label = 'В окладной ведомости не указано'

        self.index_filename = 'index.rst'

        # <root>/gubernia/index.rst
        # <root>/gubernia/<:id>/uezd/index.rst
        # <root>/gubernia/<:id>/uezd/<:id>/locality/index.rst
        # <root>/gubernia/<:id>/uezd/<:id>/volost/<:id>/index.rst
        # used in <root>/pages/gubernia/<:id>/uezd/<:id>/volost/<:id>/index.rst
        self.tree_templ = textwrap.dedent("""
        .. Tree RST template
        .. Autogenerated by gp-sphinx.py

        {_title_}

        .. toctree::
           :maxdepth: {_maxdepth_}

        {_members_}

        """)

        # <root>/gubernia/<:id>/uezd/<:id>/volost/<:id>/locality/<:id>/index.rst
        self.datasheet_templ = textwrap.dedent("""
        .. Datasheet RST template
        .. Autogenerated by gp-sphinx.py

        .. index:: {_index_}

        {_title_}

        Сельское общество
        -----------------
        {_socname_}

        Сведения о государственных крестьянах
        --------------------------------------

        .. list-table::
           :header-rows: 1
           :widths: 10 70 20

           * - #
             - Категория крестьян
             - Количество душ м.п.

        {_datasheet_}

        """)

        # <root>/gubernia/<:id>/uezd/<:id>/volost/<:id>/locality/<:id>/index.rst
        self.datasheet_empty_templ = textwrap.dedent("""
        .. Datasheet RST template
        .. Autogenerated by gp-sphinx.py

        .. index:: {_index_}

        {_title_}

        Сельское общество
        -----------------
        {_socname_}

        Сведения о государственных крестьянах
        --------------------------------------

        В окладной ведомости сведения о числе государственных крестьян отсутствуют.

        """)

        self.__current_gub = ''

    def make_dirs(self, path):
        """ Creates directories using path"""
        path = os.path.join(self.root_dir, path)
        try:
            os.makedirs(path)
        except OSError as e:
            print(f"Could not create directory: {e}")
            sys.exit(1)

    def file_write(self, fn, rst):
        """Writes RST content to file, creates one if not exists"""
        file = open(os.path.join(self.root_dir, fn), 'w+')
        file.write(rst)
        file.close()

    def clear(self):
        if os.path.exists(self.root_dir):
            shutil.rmtree(self.root_dir)

    def format3(self, name):
        """Prepend 3 wite spaces."""
        return textwrap.indent(name, '   ')

    def format_note(self, note):
        return '.. note:: \n\n%s' % self.format3(note)

    def format_header(self, name):
        """Underline header name"""
        return '%s\n' % name + ('=' * len(name))

    def format_table_row(self, cols, counter):
        _row = self.format3('* - ' + str(counter) + '\n')

        for col in cols:
            if col is not None:
                # escape newlines
                col = str(col).replace('\n', '\n\n       ')
            else:
                col = ''

            _row += self.format3('  - ' + col + '\n')

        return _row

    def __gen_gubernias(self, root_dir):
        self.cur.execute("SELECT id, name FROM gubernia ORDER BY name")
        gubernias = self.cur.fetchall()

        _g_list = ''

        for (g_id, g_name) in gubernias:
            self.__current_gub = g_name
            print("%s\tprocesing..." % self.__current_gub, end=' ', flush=True)

            _g_list += self.format3(f'gubernia/{g_id}/index\n')

            child_dir = pj(root_dir, 'gubernia', str(g_id))
            self.make_dirs(child_dir)

            self.__gen_uezds(g_id, g_name, child_dir)

            print("\r%s\tDone!       " %
                  self.__current_gub, end='\n', flush=True)

        rst = self.tree_templ.format(
            _title_=self.format_header(self.root_title),
            _members_=_g_list,
            _maxdepth_=2)

        self.file_write(pj(self.root_dir, self.index_filename), rst)

    def __gen_uezds(self, g_id, g_name, pdir):
        self.cur.execute(
            "SELECT id, name FROM uezd WHERE gub_id=? ORDER BY name", (g_id,))
        uezds = self.cur.fetchall()

        _u_list = ''

        for (u_id, u_name) in uezds:
            _u_list += self.format3(f'uezd/{u_id}/index\n')

            child_dir = pj(pdir, 'uezd', str(u_id))
            self.make_dirs(child_dir)

            self.__gen_volosts(u_id, u_name, child_dir)

        rst = self.tree_templ.format(
            _title_=self.format_header(g_name),
            _members_=_u_list,
            _maxdepth_=2)

        self.file_write(pj(pdir, self.index_filename), rst)

    def __gen_volosts(self, u_id, u_name, pdir):
        self.cur.execute(
            "SELECT id, name FROM volost WHERE uezd_id=? ORDER BY name", (u_id,))
        volosts = self.cur.fetchall()

        _v_list = ''

        for (v_id, v_name) in volosts:
            _v_list += self.format3(f'volost/{v_id}/index\n')

            child_dir = pj(pdir, 'volost', str(v_id))
            self.make_dirs(child_dir)

            self.__gen_localities(v_id, v_name, child_dir)

        rst = self.tree_templ.format(
            _title_=self.format_header(u_name),
            _members_=_v_list,
            _maxdepth_=1)

        self.file_write(pj(pdir, self.index_filename), rst)

    def __gen_localities(self, v_id, v_name, pdir):
        self.cur.execute(
            "SELECT id, name FROM locality WHERE volost_id=? ORDER BY name", (v_id,))
        localities = self.cur.fetchall()

        _l_list = ''

        for (l_id, l_name) in localities:
            _l_list += self.format3(f'locality/{l_id}/index\n')

            child_dir = pj(pdir, 'locality', str(l_id))
            self.make_dirs(child_dir)

            self.__gen_datasheets(l_id, l_name, child_dir)

        rst = self.tree_templ.format(
            _title_=self.format_header(v_name),
            _members_=_l_list,
            _maxdepth_=1)

        self.file_write(pj(pdir, self.index_filename), rst)

    def __gen_datasheets(self, l_id, l_name, pdir):
        self.cur.execute(
            "SELECT society.name FROM locality \
            LEFT JOIN society ON locality.society_id=society.id \
            WHERE locality.id=?", (l_id,))

        soc_name = self.cur.fetchall()[0][0]

        if not soc_name:
            soc_name = self.undefined_label

        self.cur.execute(
            "SELECT category.name AS category, \
            count.count AS count, count.comment AS comment \
            FROM count \
            LEFT JOIN category ON count.category_id=category.id \
            WHERE count.locality_id=? ORDER BY category.name", (l_id,))

        catcount = self.cur.fetchall()

        if catcount:
            table = ''
            comments = []

            counter = 1

            for (category, count, comment) in catcount:
                if comment is not None:
                    count = f'{str(count)}*'
                    comments.append(comment)

                table += self.format_table_row((category, count), counter)
                counter += 1

            datasheet = table

            if len(comments) > 0:
                comment_txt = ''
                comment_counter = 1
                for comm in comments:
                    comment_txt += f'({comment_counter}*) {comm}\n\n'
                    comment_counter += 1

                datasheet = f'{table}\n\n{self.format_note(comment_txt)}'

            rst = self.datasheet_templ.format(
                _index_=' '.join(l_name.split()[1:]),
                _title_=self.format_header(l_name),
                _socname_=soc_name + '.',
                _datasheet_=datasheet)

            self.file_write(pj(pdir, self.index_filename), rst)
        else:
            print("\nНет сведений о крестьянах в %s" % str(l_name))

            rst = self.datasheet_empty_templ.format(
                _index_=' '.join(l_name.split()[1:]),
                _title_=self.format_header(l_name),
                _socname_=soc_name + '.')

            self.file_write(pj(pdir, self.index_filename), rst)

    def generate(self):
        # clear data before generating
        self.clear()
        # start recursy from gubernias
        self.__gen_gubernias(self.root_dir)


def main():
    parser = argparse.ArgumentParser(
        description='GPeasantSphinx RST autogen 2020 Sakharuk Alexander')

    parser.add_argument('--db', default='gpeasant',
                        action='store', help='Database name')
    parser.add_argument('--host', default='localhost',
                        action='store', help='Database hostname')
    parser.add_argument('--port', default=3306,
                        action='store', help='Database port')
    parser.add_argument('--password', default='',
                        action='store', help='Database password')
    parser.add_argument('--user', default='root',
                        action='store', help='Database username')

    args = parser.parse_args()

    gp = GPeasantSphinx(args.user, args.password,
                        args.host, args.port, args.db)
    gp.generate()


if __name__ == '__main__':
    main()
