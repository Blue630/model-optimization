# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
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
# ==============================================================================
"""Test quantization on keras application models."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import inspect
import tempfile

from absl.testing import parameterized
import numpy as np
import tensorflow as tf

from tensorflow_model_optimization.python.core.quantization.keras import quantize
from tensorflow_model_optimization.python.core.quantization.keras import utils


class QuantizeModelsTest(tf.test.TestCase, parameterized.TestCase):

  # Derived using
  # `inspect.getmembers(tf.keras.applications, inspect.isfunction)`
  _KERAS_APPLICATION_MODELS = [
      # 'DenseNet121',
      # 'DenseNet169',
      # 'DenseNet201',
      # 'InceptionResNetV2',
      'InceptionV3',
      'MobileNet',
      'MobileNetV2',
      # 'NASNetLarge',
      # 'NASNetMobile',
      'ResNet101',
      # 'ResNet101V2',
      'ResNet152',
      # 'ResNet152V2',
      'ResNet50',
      # 'ResNet50V2',
      # 'VGG16',
      # 'VGG19',
      # 'Xception'
  ]

  _MODEL_INPUT_SHAPES = {
      'InceptionV3': (75, 75, 3)
  }

  def _batch(self, dims, batch_size):
    if dims[0] is None:
      dims[0] = batch_size
    return dims

  def _get_model(self, model_type):
    model_fn = [
        y for x, y in inspect.getmembers(tf.keras.applications)
        if x == model_type
    ][0]

    input_shape = QuantizeModelsTest._MODEL_INPUT_SHAPES.get(
        model_type, (32, 32, 3))

    return model_fn(weights=None, input_shape=input_shape)

  def _create_test_data(self, model):
    x_train = np.random.randn(
        *self._batch(model.input.get_shape().as_list(), 2)).astype('float32')
    y_train = tf.keras.utils.to_categorical(
        np.random.randint(1000, size=(2, 1)), 1000)

    return x_train, y_train

  def _verify_tflite(self, tflite_file, x_test, y_test):
    interpreter = tf.lite.Interpreter(model_path=tflite_file)
    interpreter.allocate_tensors()
    input_index = interpreter.get_input_details()[0]['index']
    output_index = interpreter.get_output_details()[0]['index']

    for x, _ in zip(x_test, y_test):
      x = x.reshape((1,) + x.shape)
      interpreter.set_tensor(input_index, x)
      interpreter.invoke()
      interpreter.get_tensor(output_index)

  @parameterized.parameters(_KERAS_APPLICATION_MODELS)
  def testModelEndToEnd(self, model_type):
    # 1. Check whether quantized model graph can be constructed.
    model = self._get_model(model_type)
    model = quantize.quantize_model(model)

    # 2. Sanity check to ensure basic training on random data works.
    x_train, y_train = self._create_test_data(model)
    model.compile(
        loss='categorical_crossentropy', optimizer='sgd', metrics=['accuracy'])
    model.fit(x_train, y_train)

    # 3. Ensure conversion to TFLite works.
    with tempfile.NamedTemporaryFile(suffix='.tflite') as t:
      with quantize.quantize_scope():
        utils.convert_keras_to_tflite(model, t.name)

      # 4. Verify input runs on converted model.
      self._verify_tflite(t.name, x_train, y_train)

  # Test the model with custom layer name prefix.
  @parameterized.product(
      model_type=_KERAS_APPLICATION_MODELS,
      name_prefix=['', 'custom_prefix_'])
  def testModelEndToEndCustomNamePrefix(self, model_type, name_prefix):
    # 1. Check whether quantized model graph can be constructed.
    model = self._get_model(model_type)
    original_layer_names = set([layer.name for layer in model.layers])

    model = quantize.quantize_model(
        model, quantized_layer_name_prefix=name_prefix)
    quantized_layer_names = set([layer.name for layer in model.layers])

    # Remove the name of layer which is newly added to quantize the input.
    quantized_layer_names.remove('quantize_layer')

    if not name_prefix or name_prefix is None:
      # The set of layer names should be the same.
      self.assertEqual(original_layer_names, quantized_layer_names)
    else:
      self.assertNotEqual(original_layer_names, quantized_layer_names)
      for name in original_layer_names:
        if name in quantized_layer_names:
          quantized_layer_names.remove(name)
        elif name_prefix + name in quantized_layer_names:
          quantized_layer_names.remove(name_prefix + name)

      self.assertEmpty(quantized_layer_names)

    # 2. Sanity check to ensure basic training on random data works.
    x_train, y_train = self._create_test_data(model)
    model.compile(
        loss='categorical_crossentropy', optimizer='sgd', metrics=['accuracy'])
    model.fit(x_train, y_train)

    # 3. Ensure conversion to TFLite works.
    with tempfile.NamedTemporaryFile(suffix='.tflite') as t:
      with quantize.quantize_scope():
        utils.convert_keras_to_tflite(model, t.name)

      # 4. Verify input runs on converted model.
      self._verify_tflite(t.name, x_train, y_train)


if __name__ == '__main__':
  tf.test.main()
