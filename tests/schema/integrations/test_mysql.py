# -*- coding: utf-8 -*-

import os
from ... import OratorTestCase
from orator import Model
from orator.orm import has_one, has_many, belongs_to, belongs_to_many, morph_to, morph_many
from orator.connections import MySqlConnection
from orator.connectors.mysql_connector import MySqlConnector
from orator.query.expression import QueryExpression


class SchemaBuilderMySqlIntegrationTestCase(OratorTestCase):

    @classmethod
    def setUpClass(cls):
        Model.set_connection_resolver(DatabaseIntegrationConnectionResolver())

    @classmethod
    def tearDownClass(cls):
        Model.unset_connection_resolver()

    def setUp(self):
        self.schema().drop_if_exists('photos')
        self.schema().drop_if_exists('posts')
        self.schema().drop_if_exists('friends')
        self.schema().drop_if_exists('users')

        with self.schema().create('users') as table:
            table.increments('id')
            table.string('email').unique()
            table.integer('votes').default(0)
            table.timestamps(use_current=True)

        with self.schema().create('friends') as table:
            table.unsigned_integer('user_id')
            table.unsigned_integer('friend_id')

            table.foreign('user_id').references('id').on('users')
            table.foreign('friend_id').references('id').on('users')

        with self.schema().create('posts') as table:
            table.increments('id')
            table.unsigned_integer('user_id')
            table.string('name').unique()
            table.timestamps(use_current=True)

            table.foreign('user_id').references('id').on('users')

        with self.schema().create('photos') as table:
            table.increments('id')
            table.morphs('imageable')
            table.string('name')
            table.timestamps(use_current=True)

        self.connection().commit()

        for i in range(10):
            user = User.create(email='user%d@foo.com' % (i + 1))

            for j in range(10):
                post = Post(name='User %d Post %d' % (user.id, j + 1))
                user.posts().save(post)

    def tearDown(self):
        post = Post.first()
        if hasattr(post, 'user_id'):
            with self.schema().table('posts') as table:
                table.drop_foreign('posts_user_id_foreign')
        elif hasattr(post, 'my_user_id'):
            with self.schema().table('posts') as table:
                table.drop_foreign('posts_my_user_id_foreign')

        with self.schema().table('friends') as table:
            table.drop_foreign('friends_user_id_foreign')
            table.drop_foreign('friends_friend_id_foreign')

        self.schema().drop('users')
        self.schema().drop('friends')
        self.schema().drop('posts')
        self.schema().drop('photos')

    def test_add_columns(self):
        with self.schema().table('posts') as table:
            table.text('content')
            table.integer('votes').default(QueryExpression(0))

        user = User.find(1)
        post = user.posts().order_by('id', 'asc').first()

        self.assertEqual('User 1 Post 1', post.name)
        self.assertEqual('', post.content)
        self.assertEqual(0, post.votes)

    def test_remove_columns(self):
        with self.schema().table('posts') as table:
            table.drop_column('name')

        self.assertIsNone(self.connection().get_column('posts', 'name'))

        user = User.find(1)
        post = user.posts().order_by('id', 'asc').first()

        self.assertFalse(hasattr(post, 'name'))

    def test_rename_columns(self):
        with self.schema().table('posts') as table:
            table.rename_column('name', 'title')

        self.assertIsNone(self.connection().get_column('posts', 'name'))
        self.assertIsNotNone(self.connection().get_column('posts', 'title'))

        user = User.find(1)
        post = user.posts().order_by('id', 'asc').first()

        self.assertEqual('User 1 Post 1', post.title)

    def test_rename_columns_with_index(self):
        with self.schema().table('users') as table:
            table.rename_column('email', 'email_address')

        self.assertIsNone(self.connection().get_column('users', 'email'))
        self.assertIsNotNone(self.connection().get_column('users', 'email_address'))

    def test_rename_columns_with_foreign_keys(self):
        with self.schema().table('posts') as table:
            table.drop_foreign('posts_user_id_foreign')
            table.rename_column('user_id', 'my_user_id')
            table.foreign('my_user_id').references('id').on('users')

        self.assertIsNone(self.connection().get_column('posts', 'user_id'))
        self.assertIsNotNone(self.connection().get_column('posts', 'my_user_id'))

    def test_change_columns(self):
        with self.schema().table('posts') as table:
            table.integer('votes').default(0)

        post = Post.find(1)
        self.assertEqual(0, post.votes)

        with self.schema().table('posts') as table:
            table.string('name').nullable().change()
            table.string('votes').default('0').change()

        name_column = self.connection().get_column('posts', 'name')
        votes_column = self.connection().get_column('posts', 'votes')
        self.assertFalse(name_column.get_notnull())
        self.assertTrue(votes_column.get_notnull())
        self.assertEqual('0', votes_column.get_default())

        post = Post.find(1)
        self.assertEqual('0', post.votes)

        with self.schema().table('users') as table:
            table.big_integer('votes').change()

    def connection(self):
        return Model.get_connection_resolver().connection()

    def schema(self):
        """
        :rtype: orator.schema.SchemaBuilder
        """
        return self.connection().get_schema_builder()


class User(Model):

    __guarded__ = []

    @belongs_to_many('friends', 'user_id', 'friend_id')
    def friends(self):
        return User

    @has_many('user_id')
    def posts(self):
        return Post

    @has_one('user_id')
    def post(self):
        return Post

    @morph_many('imageable')
    def photos(self):
        return Photo


class Post(Model):

    __guarded__ = []

    @belongs_to('user_id')
    def user(self):
        return User

    @morph_many('imageable')
    def photos(self):
        return Photo


class Photo(Model):

    __guarded__ = []

    @morph_to
    def imageable(self):
        return


class DatabaseIntegrationConnectionResolver(object):

    _connection = None

    def connection(self, name=None):
        if self._connection:
            return self._connection

        ci = os.environ.get('CI', False)
        if ci:
            database = 'orator_test'
            user = 'root'
            password = ''
        else:
            database = 'orator_test'
            user = 'orator'
            password = 'orator'

        self._connection = MySqlConnection(
            MySqlConnector().connect({
                'database': database,
                'user': user,
                'password': password
            })
        )

        return self._connection

    def get_default_connection(self):
        return 'default'

    def set_default_connection(self, name):
        pass
