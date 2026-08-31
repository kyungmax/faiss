import unittest

import faiss
import numpy as np


class TestHNSWAdaptiveLightFromEntryPoints(unittest.TestCase):
    def setUp(self):
        rng = np.random.RandomState(123)
        self.xb = rng.rand(256, 32).astype("float32")
        self.index = faiss.IndexHNSWFlat(self.xb.shape[1], 16)
        self.index.hnsw.efConstruction = 64
        self.index.add(self.xb)

    def test_uses_one_external_entry_point_per_query(self):
        query_ids = np.array([7, 33, 129], dtype=np.int64)
        queries = self.xb[query_ids]

        labels, distances = (
            self.index.knn_query_adaptive_light_from_entry_points(
                queries,
                query_ids,
                k=5,
                ef_init=32,
                enable_stop=False,
                num_threads=1,
            )
        )

        np.testing.assert_array_equal(labels[:, 0], query_ids)
        np.testing.assert_allclose(distances[:, 0], 0.0, atol=1e-6)

    def test_existing_adaptive_light_api_is_unchanged(self):
        query_ids = np.array([5, 88], dtype=np.int64)
        queries = self.xb[query_ids]

        labels, distances = self.index.knn_query_adaptive_light(
            queries,
            k=5,
            ef_init=32,
            enable_stop=False,
            num_threads=1,
        )

        self.assertEqual(labels.shape, (2, 5))
        self.assertEqual(distances.shape, (2, 5))
        np.testing.assert_array_equal(labels[:, 0], query_ids)
        np.testing.assert_allclose(distances[:, 0], 0.0, atol=1e-6)

    def test_rejects_missing_or_invalid_entry_points(self):
        queries = self.xb[[0, 1]]

        with self.assertRaises(ValueError):
            self.index.knn_query_adaptive_light_from_entry_points(
                queries,
                np.array([0], dtype=np.int64),
                k=1,
            )

        with self.assertRaises(ValueError):
            self.index.knn_query_adaptive_light_from_entry_points(
                queries,
                np.array([-1, 1], dtype=np.int64),
                k=1,
            )

        with self.assertRaises(ValueError):
            self.index.knn_query_adaptive_light_from_entry_points(
                queries,
                np.array([0, self.index.ntotal], dtype=np.int64),
                k=1,
            )

    def test_paper_bucket_and_shadow_options_share_the_new_path(self):
        query_ids = np.array([12, 64], dtype=np.int64)
        queries = self.xb[query_ids]

        labels, distances = (
            self.index
            .knn_query_adaptive_light_from_entry_points_paper_bucket(
                queries,
                query_ids,
                k=5,
                ef_init=32,
                enable_stop=True,
                num_threads=1,
                early_stop_ratio=1.0,
                paper_bucket_count=4,
                bucket_gamma_ratios=(0.75, 0.9, 1.0),
                shadow_stop_enabled=True,
                shadow_ef=16,
                shadow_early_stop_ratio=10.0,
                shadow_stop_budget=16,
            )
        )

        self.assertEqual(labels.shape, (2, 5))
        self.assertEqual(distances.shape, (2, 5))
        np.testing.assert_array_equal(labels[:, 0], query_ids)
        np.testing.assert_allclose(distances[:, 0], 0.0, atol=1e-6)

    def test_temporal_cache_uses_actual_previous_top1(self):
        query_ids = np.array([7, 7, 33, 33], dtype=np.int64)
        cache = faiss.TemporalQueryCache(32, 32, 0.9999)

        labels, distances, hits, cosines, entry_points = (
            self.index.knn_query_adaptive_light_temporal(
                self.xb[query_ids],
                cache,
                k=5,
                ef_init=32,
                enable_stop=False,
                num_threads=1,
            )
        )

        np.testing.assert_array_equal(labels[:, 0], query_ids)
        np.testing.assert_allclose(distances[:, 0], 0.0, atol=1e-6)
        np.testing.assert_array_equal(hits, [0, 1, 0, 1])
        self.assertTrue(np.isnan(cosines[0]))
        self.assertGreaterEqual(float(cosines[1]), 0.9999)
        self.assertGreaterEqual(float(cosines[3]), 0.9999)
        np.testing.assert_array_equal(
            entry_points,
            [-1, labels[0, 0], -1, labels[2, 0]],
        )
        self.assertEqual(cache.dimension(), 32)
        self.assertEqual(cache.capacity(), 32)
        self.assertEqual(cache.size(), 4)
        self.assertEqual(cache.queries_seen(), 4)
        self.assertEqual(cache.hit_count(), 2)
        self.assertAlmostEqual(cache.hit_rate(), 0.5)

        cache.reset()
        self.assertEqual(cache.size(), 0)
        self.assertEqual(cache.queries_seen(), 0)
        self.assertEqual(cache.hit_count(), 0)

    def test_temporal_paper_bucket_and_shadow_options(self):
        query_ids = np.array([12, 12], dtype=np.int64)
        cache = faiss.TemporalQueryCache(32, 32, 0.9999)

        labels, distances, hits, cosines, entry_points = (
            self.index.knn_query_sage_temporal(
                self.xb[query_ids],
                cache,
                k=5,
                ef_init=32,
                enable_stop=True,
                num_threads=1,
                early_stop_ratio=1.0,
                paper_bucket_count=4,
                bucket_gamma_ratios=(0.75, 0.9, 1.0),
                shadow_stop_enabled=True,
                shadow_ef=16,
                shadow_early_stop_ratio=10.0,
                shadow_stop_budget=16,
            )
        )

        np.testing.assert_array_equal(labels[:, 0], query_ids)
        np.testing.assert_allclose(distances[:, 0], 0.0, atol=1e-6)
        np.testing.assert_array_equal(hits, [0, 1])
        self.assertTrue(np.isnan(cosines[0]))
        self.assertGreaterEqual(float(cosines[1]), 0.9999)
        np.testing.assert_array_equal(entry_points, [-1, labels[0, 0]])

    def test_temporal_cache_rejects_wrong_dimension(self):
        cache = faiss.TemporalQueryCache(16, 32, 0.8)

        with self.assertRaises(RuntimeError):
            self.index.knn_query_adaptive_light_temporal(
                self.xb[[0]],
                cache,
                k=1,
                ef_init=32,
                enable_stop=False,
                num_threads=1,
            )


if __name__ == "__main__":
    unittest.main()
