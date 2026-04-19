#### What this does ####
#   picks based on response time (for streaming, this is time to first token)
from datetime import datetime, timedelta
import random
from typing import Dict, List, Optional, Union

import litellm
from litellm import ModelResponse, token_counter, verbose_logger
from litellm._logging import verbose_router_logger
from litellm.caching.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger


class LowestCostLoggingHandler(CustomLogger):
    test_flag: bool = False
    logged_success: int = 0
    logged_failure: int = 0

    def __init__(self, router_cache: DualCache, routing_args: dict = {}):
        self.router_cache = router_cache

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            """
            Update usage on success
            """
            if kwargs["litellm_params"].get("metadata") is None:
                pass
            else:
                model_group = kwargs["litellm_params"]["metadata"].get(
                    "model_group", None
                )

                id = kwargs["litellm_params"].get("model_info", {}).get("id", None)
                if model_group is None or id is None:
                    return
                elif isinstance(id, int):
                    id = str(id)

                # ------------
                # Setup values
                # ------------
                """
                {
                    {model_group}_map: {
                        id: {
                            f"{date:hour:minute}" : {"tpm": 34, "rpm": 3}
                        }
                    }
                }
                """
                now = datetime.now()
                current_date = now.strftime("%Y-%m-%d")
                current_hour = now.strftime("%H")
                current_minute = now.strftime("%M")
                precise_minute = f"{current_date}-{current_hour}-{current_minute}"
                precise_5s = f"{now.strftime('%Y-%m-%d-%H-%M')}-{(now.second // 5) * 5}"
                cost_key = f"{model_group}_map"

                response_ms: timedelta = end_time - start_time

                total_tokens = 0

                if isinstance(response_obj, ModelResponse):
                    _usage = getattr(response_obj, "usage", None)
                    if _usage is not None and isinstance(_usage, litellm.Usage):
                        completion_tokens = _usage.completion_tokens
                        total_tokens = _usage.total_tokens
                        float(response_ms.total_seconds() / completion_tokens)

                # ------------
                # Update usage
                # ------------

                request_count_dict = self.router_cache.get_cache(key=cost_key) or {}

                # check local result first

                if id not in request_count_dict:
                    request_count_dict[id] = {}

                if precise_5s not in request_count_dict[id]:
                    request_count_dict[id][precise_5s] = {}
                if precise_minute not in request_count_dict[id]:
                    request_count_dict[id][precise_minute] = {}

                ## TPM
                request_count_dict[id][precise_5s]["tpm"] = (
                    request_count_dict[id][precise_5s].get("tpm", 0) + total_tokens
                )
                request_count_dict[id][precise_minute]["tpm"] = (
                    request_count_dict[id][precise_minute].get("tpm", 0) + total_tokens
                )

                ## RPM
                request_count_dict[id][precise_5s]["rpm"] = (
                    request_count_dict[id][precise_5s].get("rpm", 0) + 1
                )
                request_count_dict[id][precise_minute]["rpm"] = (
                    request_count_dict[id][precise_minute].get("rpm", 0) + 1
                )

                self.router_cache.set_cache(key=cost_key, value=request_count_dict)

                ### TESTING ###
                if self.test_flag:
                    self.logged_success += 1
        except Exception as e:
            verbose_logger.exception(
                "litellm.router_strategy.lowest_cost.py::log_success_event(): Exception occured - {}".format(
                    str(e)
                )
            )
            pass

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            """
            Update cost usage on success
            """
            if kwargs["litellm_params"].get("metadata") is None:
                pass
            else:
                model_group = kwargs["litellm_params"]["metadata"].get(
                    "model_group", None
                )

                id = kwargs["litellm_params"].get("model_info", {}).get("id", None)
                if model_group is None or id is None:
                    return
                elif isinstance(id, int):
                    id = str(id)

                # ------------
                # Setup values
                # ------------
                """
                {
                    {model_group}_map: {
                        id: {
                            "cost": [..]
                            f"{date:hour:minute}" : {"tpm": 34, "rpm": 3}
                        }
                    }
                }
                """
                cost_key = f"{model_group}_map"

                now = datetime.now()
                precise_minute = f"{now.strftime('%Y-%m-%d-%H-%M')}"
                precise_5s = f"{now.strftime('%Y-%m-%d-%H-%M')}-{(now.second // 5) * 5}"

                response_ms: timedelta = end_time - start_time

                total_tokens = 0

                if isinstance(response_obj, ModelResponse):
                    _usage = getattr(response_obj, "usage", None)
                    if _usage is not None and isinstance(_usage, litellm.Usage):
                        completion_tokens = _usage.completion_tokens
                        total_tokens = _usage.total_tokens

                        float(response_ms.total_seconds() / completion_tokens)

                # ------------
                # Update usage
                # ------------

                request_count_dict = (
                    await self.router_cache.async_get_cache(key=cost_key) or {}
                )

                if id not in request_count_dict:
                    request_count_dict[id] = {}
                if precise_5s not in request_count_dict[id]:
                    request_count_dict[id][precise_5s] = {}
                if precise_minute not in request_count_dict[id]:
                    request_count_dict[id][precise_minute] = {}

                ## TPM
                request_count_dict[id][precise_5s]["tpm"] = (
                    request_count_dict[id][precise_5s].get("tpm", 0) + total_tokens
                )
                request_count_dict[id][precise_minute]["tpm"] = (
                    request_count_dict[id][precise_minute].get("tpm", 0) + total_tokens
                )

                ## RPM
                request_count_dict[id][precise_5s]["rpm"] = (
                    request_count_dict[id][precise_5s].get("rpm", 0) + 1
                )
                request_count_dict[id][precise_minute]["rpm"] = (
                    request_count_dict[id][precise_minute].get("rpm", 0) + 1
                )

                await self.router_cache.async_set_cache(
                    key=cost_key, value=request_count_dict
                )  # reset map within window

                ### TESTING ###
                if self.test_flag:
                    self.logged_success += 1
        except Exception as e:
            verbose_logger.exception(
                "litellm.proxy.hooks.prompt_injection_detection.py::async_pre_call_hook(): Exception occured - {}".format(
                    str(e)
                )
            )
            pass

    async def async_get_available_deployments(  # noqa: PLR0915
        self,
        model_group: str,
        healthy_deployments: list,
        messages: Optional[List[Dict[str, str]]] = None,
        input: Optional[Union[str, List]] = None,
        request_kwargs: Optional[Dict] = None,
    ):
        """
        Returns a deployment with the lowest cost
        """
        cost_key = f"{model_group}_map"

        request_count_dict = await self.router_cache.async_get_cache(key=cost_key) or {}

        # -----------------------
        # Find lowest used model
        # ----------------------
        float("inf")

        now = datetime.now()

        # 1-minute window
        precise_minute = f"{now.strftime('%Y-%m-%d-%H-%M')}"
        prev_min_dt = now - timedelta(minutes=1)
        precise_minute_prev = f"{prev_min_dt.strftime('%Y-%m-%d-%H-%M')}"
        time_into_min = now.second + (now.microsecond / 1000000.0)
        weight_min = (60.0 - time_into_min) / 60.0

        # 5-second window
        precise_5s = f"{now.strftime('%Y-%m-%d-%H-%M')}-{(now.second // 5) * 5}"
        prev_5s_dt = now - timedelta(seconds=5)
        precise_5s_prev = (
            f"{prev_5s_dt.strftime('%Y-%m-%d-%H-%M')}-{(prev_5s_dt.second // 5) * 5}"
        )
        time_into_5s = (now.second % 5) + (now.microsecond / 1000000.0)
        weight_5s = (5.0 - time_into_5s) / 5.0

        if request_count_dict is None:  # base case
            return

        all_deployments = request_count_dict
        for d in healthy_deployments:
            ## if healthy deployment not yet used
            if d["model_info"]["id"] not in all_deployments:
                all_deployments[d["model_info"]["id"]] = {
                    precise_5s: {"tpm": 0, "rpm": 0},
                    precise_minute: {"tpm": 0, "rpm": 0},
                }

        try:
            input_tokens = token_counter(messages=messages, text=input)
        except Exception:
            input_tokens = 0

        # randomly sample from all_deployments, incase all deployments have latency=0.0
        _items = random.sample(list(all_deployments.items()), len(all_deployments))

        ### GET AVAILABLE DEPLOYMENTS ### filter out any deployments > tpm/rpm limits
        potential_deployments = []
        _cost_per_deployment = {}
        for item, item_map in _items:
            ## get the item from model list
            _deployment = None
            for m in healthy_deployments:
                if item == m["model_info"]["id"]:
                    _deployment = m

            if _deployment is None:
                continue  # skip to next one

            _deployment_tpm = (
                _deployment.get("tpm", None)
                or _deployment.get("litellm_params", {}).get("tpm", None)
                or _deployment.get("model_info", {}).get("tpm", None)
                or float("inf")
            )

            _deployment_rpm = (
                _deployment.get("rpm", None)
                or _deployment.get("litellm_params", {}).get("rpm", None)
                or _deployment.get("model_info", {}).get("rpm", None)
                or float("inf")
            )
            item_litellm_model_name = _deployment.get("litellm_params", {}).get("model")
            item_litellm_model_cost_map = litellm.model_cost.get(
                item_litellm_model_name, {}
            )

            # check if user provided input_cost_per_token and output_cost_per_token in litellm_params
            item_input_cost = None
            item_output_cost = None
            if _deployment.get("litellm_params", {}).get("input_cost_per_token", None):
                item_input_cost = _deployment.get("litellm_params", {}).get(
                    "input_cost_per_token"
                )

            if _deployment.get("litellm_params", {}).get("output_cost_per_token", None):
                item_output_cost = _deployment.get("litellm_params", {}).get(
                    "output_cost_per_token"
                )

            if item_input_cost is None:
                item_input_cost = item_litellm_model_cost_map.get(
                    "input_cost_per_token", 5.0
                )

            if item_output_cost is None:
                item_output_cost = item_litellm_model_cost_map.get(
                    "output_cost_per_token", 5.0
                )

            # if litellm["model"] is not in model_cost map -> use item_cost = $10

            item_cost = item_input_cost + item_output_cost

            # Calculate metrics using 5 second sliding window approximation
            curr_rpm_5s = item_map.get(precise_5s, {}).get("rpm", 0)
            prev_rpm_5s = item_map.get(precise_5s_prev, {}).get("rpm", 0)
            item_rpm = curr_rpm_5s + prev_rpm_5s * weight_5s

            curr_tpm_5s = item_map.get(precise_5s, {}).get("tpm", 0)
            prev_tpm_5s = item_map.get(precise_5s_prev, {}).get("tpm", 0)
            item_tpm = curr_tpm_5s + prev_tpm_5s * weight_5s

            # Calculate metrics using 1 minute sliding window approximation
            curr_rpm_min = item_map.get(precise_minute, {}).get("rpm", 0)
            prev_rpm_min = item_map.get(precise_minute_prev, {}).get("rpm", 0)
            item_rpm_minute = curr_rpm_min + prev_rpm_min * weight_min

            curr_tpm_min = item_map.get(precise_minute, {}).get("tpm", 0)
            prev_tpm_min = item_map.get(precise_minute_prev, {}).get("tpm", 0)
            item_tpm_minute = curr_tpm_min + prev_tpm_min * weight_min

            # Get 5-second limits: use rp5s / tp5s if provided, else fallback to rpm/tpm divided by 12 (since 60s / 5s = 12 buckets)
            _deployment_rp5s = (
                _deployment.get("rp5s", None)
                or _deployment.get("litellm_params", {}).get("rp5s", None)
                or _deployment.get("model_info", {}).get("rp5s", None)
                or (_deployment_rpm / 12.0)
            )

            _deployment_tp5s = (
                _deployment.get("tp5s", None)
                or _deployment.get("litellm_params", {}).get("tp5s", None)
                or _deployment.get("model_info", {}).get("tp5s", None)
                or (_deployment_tpm / 12.0)
            )

            verbose_router_logger.debug(
                f"item_cost: {item_cost}, item_tpm_5s: {item_tpm}, item_rpm_5s: {item_rpm}, model_id: {_deployment.get('model_info', {}).get('id')}"
            )

            # -------------- #
            # Debugging Logic
            # -------------- #
            # We use _cost_per_deployment to log to langfuse, slack - this is not used to make a decision on routing
            # this helps a user to debug why the router picked a specfic deployment      #
            _deployment_api_base = _deployment.get("litellm_params", {}).get(
                "api_base", ""
            )
            if _deployment_api_base is not None:
                _cost_per_deployment[_deployment_api_base] = item_cost
            # -------------- #
            # End of Debugging Logic
            # -------------- #

            if (
                item_tpm + input_tokens > _deployment_tp5s
                or item_rpm + 1 > _deployment_rp5s
                or item_tpm_minute + input_tokens > _deployment_tpm
                or item_rpm_minute + 1 > _deployment_rpm
            ):  # if user passed in limits in the model_list
                continue
            else:
                potential_deployments.append((_deployment, item_cost))

        if len(potential_deployments) == 0:
            return None

        potential_deployments = sorted(potential_deployments, key=lambda x: x[1])

        selected_deployment = potential_deployments[0][0]
        return selected_deployment
