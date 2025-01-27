# coding=utf-8
# Copyright 2021 the HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copyfile

from huggingface_hub import Repository, delete_repo, login
from requests.exceptions import HTTPError
from transformers import AutoProcessor, AutoTokenizer, Wav2Vec2Config, Wav2Vec2FeatureExtractor, Wav2Vec2Processor
from transformers.file_utils import FEATURE_EXTRACTOR_NAME, is_tokenizers_available
from transformers.testing_utils import PASS, USER, is_staging_test
from transformers.tokenization_utils import TOKENIZER_CONFIG_FILE


sys.path.append(str(Path(__file__).parent.parent / "utils"))

from test_module.custom_feature_extraction import CustomFeatureExtractor  # noqa E402
from test_module.custom_processing import CustomProcessor  # noqa E402
from test_module.custom_tokenization import CustomTokenizer  # noqa E402


SAMPLE_PROCESSOR_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures/dummy_feature_extractor_config.json"
)
SAMPLE_VOCAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures/vocab.json")

SAMPLE_FEATURE_EXTRACTION_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class AutoFeatureExtractorTest(unittest.TestCase):
    def test_processor_from_model_shortcut(self):
        processor = AutoProcessor.from_pretrained("facebook/wav2vec2-base-960h")
        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_processor_from_local_directory_from_repo(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            model_config = Wav2Vec2Config()
            processor = AutoProcessor.from_pretrained("facebook/wav2vec2-base-960h")

            # save in new folder
            model_config.save_pretrained(tmpdirname)
            processor.save_pretrained(tmpdirname)

            processor = AutoProcessor.from_pretrained(tmpdirname)

        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_processor_from_local_directory_from_extractor_config(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            # copy relevant files
            copyfile(SAMPLE_PROCESSOR_CONFIG, os.path.join(tmpdirname, FEATURE_EXTRACTOR_NAME))
            copyfile(SAMPLE_VOCAB, os.path.join(tmpdirname, "vocab.json"))

            processor = AutoProcessor.from_pretrained(tmpdirname)

        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_processor_from_feat_extr_processor_class(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            feature_extractor = Wav2Vec2FeatureExtractor()
            tokenizer = AutoTokenizer.from_pretrained("facebook/wav2vec2-base-960h")

            processor = Wav2Vec2Processor(feature_extractor, tokenizer)

            # save in new folder
            processor.save_pretrained(tmpdirname)

            # drop `processor_class` in tokenizer
            with open(os.path.join(tmpdirname, TOKENIZER_CONFIG_FILE), "r") as f:
                config_dict = json.load(f)
                config_dict.pop("processor_class")

            with open(os.path.join(tmpdirname, TOKENIZER_CONFIG_FILE), "w") as f:
                f.write(json.dumps(config_dict))

            processor = AutoProcessor.from_pretrained(tmpdirname)

        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_processor_from_tokenizer_processor_class(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            feature_extractor = Wav2Vec2FeatureExtractor()
            tokenizer = AutoTokenizer.from_pretrained("facebook/wav2vec2-base-960h")

            processor = Wav2Vec2Processor(feature_extractor, tokenizer)

            # save in new folder
            processor.save_pretrained(tmpdirname)

            # drop `processor_class` in feature extractor
            with open(os.path.join(tmpdirname, FEATURE_EXTRACTOR_NAME), "r") as f:
                config_dict = json.load(f)
                config_dict.pop("processor_class")

            with open(os.path.join(tmpdirname, FEATURE_EXTRACTOR_NAME), "w") as f:
                f.write(json.dumps(config_dict))

            processor = AutoProcessor.from_pretrained(tmpdirname)

        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_processor_from_local_directory_from_model_config(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            model_config = Wav2Vec2Config(processor_class="Wav2Vec2Processor")
            model_config.save_pretrained(tmpdirname)
            # copy relevant files
            copyfile(SAMPLE_VOCAB, os.path.join(tmpdirname, "vocab.json"))
            # create emtpy sample processor
            with open(os.path.join(tmpdirname, FEATURE_EXTRACTOR_NAME), "w") as f:
                f.write("{}")

            processor = AutoProcessor.from_pretrained(tmpdirname)

        self.assertIsInstance(processor, Wav2Vec2Processor)

    def test_from_pretrained_dynamic_processor(self):
        processor = AutoProcessor.from_pretrained("hf-internal-testing/test_dynamic_processor", trust_remote_code=True)
        self.assertTrue(processor.special_attribute_present)
        self.assertEqual(processor.__class__.__name__, "NewProcessor")

        feature_extractor = processor.feature_extractor
        self.assertTrue(feature_extractor.special_attribute_present)
        self.assertEqual(feature_extractor.__class__.__name__, "NewFeatureExtractor")

        tokenizer = processor.tokenizer
        self.assertTrue(tokenizer.special_attribute_present)
        if is_tokenizers_available():
            self.assertEqual(tokenizer.__class__.__name__, "NewTokenizerFast")

            # Test we can also load the slow version
            processor = AutoProcessor.from_pretrained(
                "hf-internal-testing/test_dynamic_processor", trust_remote_code=True, use_fast=False
            )
            tokenizer = processor.tokenizer
            self.assertTrue(tokenizer.special_attribute_present)
            self.assertEqual(tokenizer.__class__.__name__, "NewTokenizer")
        else:
            self.assertEqual(tokenizer.__class__.__name__, "NewTokenizer")


@is_staging_test
class ProcessorPushToHubTester(unittest.TestCase):
    vocab_tokens = ["[UNK]", "[CLS]", "[SEP]", "[PAD]", "[MASK]", "bla", "blou"]

    @classmethod
    def setUpClass(cls):
        cls._token = login(username=USER, password=PASS)

    @classmethod
    def tearDownClass(cls):
        try:
            delete_repo(token=cls._token, name="test-dynamic-processor")
        except HTTPError:
            pass

    def test_push_to_hub_dynamic_processor(self):
        CustomFeatureExtractor.register_for_auto_class()
        CustomTokenizer.register_for_auto_class()
        CustomProcessor.register_for_auto_class()

        feature_extractor = CustomFeatureExtractor.from_pretrained(SAMPLE_FEATURE_EXTRACTION_CONFIG_DIR)

        with tempfile.TemporaryDirectory() as tmp_dir:
            vocab_file = os.path.join(tmp_dir, "vocab.txt")
            with open(vocab_file, "w", encoding="utf-8") as vocab_writer:
                vocab_writer.write("".join([x + "\n" for x in self.vocab_tokens]))
            tokenizer = CustomTokenizer(vocab_file)

        processor = CustomProcessor(feature_extractor, tokenizer)

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Repository(tmp_dir, clone_from=f"{USER}/test-dynamic-processor", use_auth_token=self._token)
            processor.save_pretrained(tmp_dir)

            # This has added the proper auto_map field to the feature extractor config
            self.assertDictEqual(
                processor.feature_extractor.auto_map,
                {
                    "AutoFeatureExtractor": "custom_feature_extraction.CustomFeatureExtractor",
                    "AutoProcessor": "custom_processing.CustomProcessor",
                },
            )

            # This has added the proper auto_map field to the tokenizer config
            with open(os.path.join(tmp_dir, "tokenizer_config.json")) as f:
                tokenizer_config = json.load(f)
            self.assertDictEqual(
                tokenizer_config["auto_map"],
                {
                    "AutoTokenizer": ["custom_tokenization.CustomTokenizer", None],
                    "AutoProcessor": "custom_processing.CustomProcessor",
                },
            )

            # The code has been copied from fixtures
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "custom_feature_extraction.py")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "custom_tokenization.py")))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "custom_processing.py")))

            repo.push_to_hub()

        new_processor = AutoProcessor.from_pretrained(f"{USER}/test-dynamic-processor", trust_remote_code=True)
        # Can't make an isinstance check because the new_processor is from the CustomProcessor class of a dynamic module
        self.assertEqual(new_processor.__class__.__name__, "CustomProcessor")
