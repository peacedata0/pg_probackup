import os
import unittest
from .helpers.ptrack_helpers import ProbackupTest, ProbackupException
from datetime import datetime, timedelta
import subprocess
from testgres import ClusterException
import shutil, sys


module_name = 'ptrack'


class PtrackBackupTest(ProbackupTest, unittest.TestCase):

    # @unittest.skip("skip")
    # @unittest.expectedFailure
    def test_ptrack_enable(self):
        """make ptrack without full backup, should result in error"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s'}
            )
        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        self.set_archiving(backup_dir, 'node', node)
        node.start()

        # PTRACK BACKUP
        try:
            self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
            # we should die here because exception is what we expect to happen
            self.assertEqual(1, 0, "Expecting Error because ptrack disabled.\n Output: {0} \n CMD: {1}".format(
                repr(self.output), self.cmd))
        except ProbackupException as e:
            self.assertEqual('ERROR: Ptrack is disabled\n', e.message,
                '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(e.message), self.cmd))

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_ptrack_stream(self):
        """make node, make full and ptrack stream backups, restore them and check data correctness"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create sequence t_seq")
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, nextval('t_seq') as t_seq, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        full_result = node.safe_psql("postgres", "SELECT * FROM t_heap")
        full_backup_id = self.backup_node(backup_dir, 'node', node, options=['--stream'])

        # PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, nextval('t_seq') as t_seq, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(100,200) i")
        ptrack_result = node.safe_psql("postgres", "SELECT * FROM t_heap")
        ptrack_backup_id = self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=['--stream'])

        # Drop Node
        node.cleanup()

        # Restore and check full backup
        self.assertIn("INFO: Restore of backup {0} completed.".format(full_backup_id),
            self.restore_node(backup_dir, 'node', node, backup_id=full_backup_id, options=["-j", "4"]),
            '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(self.output), self.cmd))
        node.start()
        full_result_new = node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.assertEqual(full_result, full_result_new)
        node.cleanup()

        # Restore and check ptrack backup
        self.assertIn("INFO: Restore of backup {0} completed.".format(ptrack_backup_id),
            self.restore_node(backup_dir, 'node', node, backup_id=ptrack_backup_id, options=["-j", "4"]),
            '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(self.output), self.cmd))
        node.start()
        ptrack_result_new = node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.assertEqual(ptrack_result, ptrack_result_new)

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_ptrack_archive(self):
        """make archive node, make full and ptrack backups, check data correctness in restored instance"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        self.set_archiving(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        full_result = node.safe_psql("postgres", "SELECT * FROM t_heap")
        full_backup_id = self.backup_node(backup_dir, 'node', node)

        # PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(100,200) i")
        ptrack_result = node.safe_psql("postgres", "SELECT * FROM t_heap")
        ptrack_backup_id = self.backup_node(backup_dir, 'node', node, backup_type='ptrack')

        # Drop Node
        node.cleanup()

        # Check full backup
        self.assertIn("INFO: Restore of backup {0} completed.".format(full_backup_id),
            self.restore_node(backup_dir, 'node', node, backup_id=full_backup_id, options=["-j", "4"]),
            '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(self.output), self.cmd))
        node.start()
        full_result_new = node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.assertEqual(full_result, full_result_new)
        node.cleanup()

        # Check ptrack backup
        self.assertIn("INFO: Restore of backup {0} completed.".format(ptrack_backup_id),
            self.restore_node(backup_dir, 'node', node, backup_id=ptrack_backup_id, options=["-j", "4"]),
            '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(self.output), self.cmd))
        node.start()
        ptrack_result_new = node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.assertEqual(ptrack_result, ptrack_result_new)
        node.cleanup()

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_ptrack_pgpro417(self):
        """Make  node, take full backup, take ptrack backup, delete ptrack backup. Try to take ptrack backup, which should fail"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        backup_id = self.backup_node(backup_dir, 'node', node, backup_type='full', options=["--stream"])
        start_lsn_full = self.show_pb(backup_dir, 'node', backup_id)['start-lsn']

        # PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(100,200) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        backup_id = self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
        start_lsn_ptrack = self.show_pb(backup_dir, 'node', backup_id)['start-lsn']

        self.delete_pb(backup_dir, 'node', backup_id)

        # SECOND PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(200,300) i")

        try:
            self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
            # we should die here because exception is what we expect to happen
            self.assertEqual(1, 0, "Expecting Error because of LSN mismatch from ptrack_control and previous backup start_lsn.\n Output: {0} \n CMD: {1}".format(
                repr(self.output), self.cmd))
        except ProbackupException as e:
            self.assertTrue('ERROR: LSN from ptrack_control' in e.message
                 and 'differs from LSN of previous backup' in e.message,
                '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(e.message), self.cmd))

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_page_pgpro417(self):
        """Make archive node, take full backup, take page backup, delete page backup. Try to take ptrack backup, which should fail"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        self.set_archiving(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.backup_node(backup_dir, 'node', node)

        # PAGE BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(100,200) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        backup_id = self.backup_node(backup_dir, 'node', node, backup_type='page')

        self.delete_pb(backup_dir, 'node', backup_id)

        # PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(200,300) i")

        try:
            self.backup_node(backup_dir, 'node', node, backup_type='ptrack')
            # we should die here because exception is what we expect to happen
            self.assertEqual(1, 0, "Expecting Error because of LSN mismatch from ptrack_control and previous backup start_lsn.\n Output: {0} \n CMD: {1}".format(
                repr(self.output), self.cmd))
        except ProbackupException as e:
            self.assertTrue('ERROR: LSN from ptrack_control' in e.message
                 and 'differs from LSN of previous backup' in e.message,
                '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(e.message), self.cmd))

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_full_pgpro417(self):
        """Make node, take two full backups, delete full second backup. Try to take ptrack backup, which should fail"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.backup_node(backup_dir, 'node', node, options=["--stream"])

        # SECOND FULL BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(100,200) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        backup_id = self.backup_node(backup_dir, 'node', node, options=["--stream"])

        self.delete_pb(backup_dir, 'node', backup_id)

        # PTRACK BACKUP
        node.safe_psql(
            "postgres",
            "insert into t_heap select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(200,300) i")
        try:
            self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
            # we should die here because exception is what we expect to happen
            self.assertEqual(1, 0, "Expecting Error because of LSN mismatch from ptrack_control and previous backup start_lsn.\n Output: {0} \n CMD: {1}".format(
                repr(self.output), self.cmd))
        except ProbackupException as e:
            self.assertTrue('ERROR: LSN from ptrack_control' in e.message
                 and 'differs from LSN of previous backup' in e.message
                 and 'Create new full backup before an incremental one' in e.message,
                '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(e.message), self.cmd))

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_create_db(self):
        """Make node, take full backup, create database db1, take ptrack backup, restore database and check it presense"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        # FULL BACKUP
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        node.safe_psql("postgres", "SELECT * FROM t_heap")
        self.backup_node(backup_dir, 'node', node, options=["--stream"])

        # CREATE DATABASE DB1
        node.safe_psql(
            "postgres", "create database db1")
#        node.safe_psql("db1", "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
#        result =  node.safe_psql("db1", "select * from t_heap")

        # PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
        pgdata_content = self.pgdata_content(node.data_dir)

        # DROP DATABASE DB1
        #node.safe_psql(
        #    "postgres", "drop database db1")
        # SECOND PTRACK BACKUP
        #self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])
        node_restored = self.make_simple_node(base_dir="{0}/{1}/node_restored".format(module_name, fname))
        node_restored.cleanup()

        self.restore_node(backup_dir, 'node', node_restored, options=["-j", "4"])
        pgdata_content_new = self.pgdata_content(node_restored.data_dir)
        self.compare_pgdata(pgdata_content, pgdata_content_new)
        result_new =  node_restored.safe_psql("db1", "select * from t_heap")

        self.assertEqual(result, result_new)
        try:
            node_restored.safe_psql('db1', 'select 1')
            # we should die here because exception is what we expect to happen
            self.assertEqual(1, 0, "Expecting Error because we are connecting to deleted database.\n Output: {0} \n CMD: {1}".format(
                repr(self.output), self.cmd))
        except ClusterException as e:
            self.assertTrue('FATAL:  database "db1" does not exist' in e.message,
                '\n Unexpected Error Message: {0}\n CMD: {1}'.format(repr(e.message), self.cmd))

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_drop_tablespace(self):
        """Make node, create table, alter table tablespace, take ptrack backup, move table from tablespace, take ptrack backup"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        self.create_tblspace_in_node(node, 'somedata')

        # CREATE TABLE
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        result = node.safe_psql("postgres", "select * from t_heap")
        # FULL BACKUP
        self.backup_node(backup_dir, 'node', node, options=["--stream"])

        # Move table to tablespace 'somedata'
        node.safe_psql(
            "postgres", "alter table t_heap set tablespace somedata")
        # PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])

        # Move table back to default tablespace
        node.safe_psql(
            "postgres", "alter table t_heap set tablespace pg_default")
        # SECOND PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])

        # DROP TABLESPACE 'somedata'
        node.safe_psql(
            "postgres", "drop tablespace somedata")
        # THIRD PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])

        tblspace = self.get_tblspace_path(node, 'somedata')
        node.cleanup()
        shutil.rmtree(tblspace, ignore_errors=True)
        self.restore_node(backup_dir, 'node', node, options=["-j", "4"])
        node.start()

        tblspc_exist = node.safe_psql("postgres", "select exists(select 1 from pg_tablespace where spcname = 'somedata')")
        if tblspc_exist.rstrip() == 't':
            self.assertEqual(1, 0, "Expecting Error because tablespace 'somedata' should not be present")

        result_new = node.safe_psql("postgres", "select * from t_heap")
        self.assertEqual(result, result_new)

        # Clean after yourself
        self.del_test_dir(module_name, fname)

    # @unittest.skip("skip")
    def test_alter_tablespace(self):
        """Make node, create table, alter table tablespace, take ptrack backup, move table from tablespace, take ptrack backup"""
        self.maxDiff = None
        fname = self.id().split('.')[3]
        backup_dir = os.path.join(self.tmp_path, module_name, fname, 'backup')
        node = self.make_simple_node(base_dir="{0}/{1}/node".format(module_name, fname),
            set_replication=True,
            initdb_params=['--data-checksums'],
            pg_options={'wal_level': 'replica', 'max_wal_senders': '2', 'checkpoint_timeout': '30s', 'ptrack_enable': 'on'}
            )

        self.init_pb(backup_dir)
        self.add_instance(backup_dir, 'node', node)
        node.start()

        self.create_tblspace_in_node(node, 'somedata')

        # CREATE TABLE
        node.safe_psql(
            "postgres",
            "create table t_heap as select i as id, md5(i::text) as text, md5(i::text)::tsvector as tsvector from generate_series(0,100) i")
        result = node.safe_psql("postgres", "select * from t_heap")
        # FULL BACKUP
        self.backup_node(backup_dir, 'node', node, options=["--stream"])

        # Move table to separate tablespace
        node.safe_psql(
            "postgres", "alter table t_heap set tablespace somedata")
        # FIRTS PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])

        # Restore ptrack backup and check table consistency
        restored_node = self.make_simple_node(base_dir="{0}/{1}/restored_node".format(module_name, fname))
        restored_node.cleanup()
        tblspc_path = self.get_tblspace_path(node, 'somedata')
        tblspc_path_new = self.get_tblspace_path(restored_node, 'somedata_restored')
        self.restore_node(backup_dir, 'node', restored_node, options=[
            "-j", "4", "-T", "{0}={1}".format(tblspc_path, tblspc_path_new)])
        restored_node.append_conf("postgresql.auto.conf", "port = {0}".format(restored_node.port))
        restored_node.start()

        result_new = restored_node.safe_psql("postgres", "select * from t_heap")
        self.assertEqual(result, result_new)
        restored_node.cleanup()
        shutil.rmtree(tblspc_path_new, ignore_errors=True)

        # Move table to default tablespace
        node.safe_psql(
            "postgres", "alter table t_heap set tablespace pg_default")
        # SECOND PTRACK BACKUP
        self.backup_node(backup_dir, 'node', node, backup_type='ptrack', options=["--stream"])

        # Restore second ptrack backup and check table consistency
        self.restore_node(backup_dir, 'node', restored_node, options=[
            "-j", "4", "-T", "{0}={1}".format(tblspc_path, tblspc_path_new)])
        restored_node.append_conf("postgresql.auto.conf", "port = {0}".format(restored_node.port))
        restored_node.start()
        result_new = restored_node.safe_psql("postgres", "select * from t_heap")
        self.assertEqual(result, result_new)

        # Clean after yourself
        self.del_test_dir(module_name, fname)