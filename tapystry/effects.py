from tapystry import Effect, Strand, Call, Send, Receive, CallFork, First, Cancel


def Sequence(effects, name=None):
    """Do each of the effects.
    Effects can be a (nested) list/dict structure
    """
    def sequence():
        if isinstance(effects, Effect):
            val = yield effects
            return val
        if isinstance(effects, list):
            results = []
            for effect in effects:
                if isinstance(effect, (list, dict)):
                    result = yield Sequence(effect, name)
                else:
                    result = yield effect
                results.append(result)
        else:
            assert isinstance(effects, dict)
            results = dict()
            for k, effect in effects.items():
                if isinstance(effect, (list, dict)):
                    result = yield Sequence(effect, name)
                else:
                    result = yield effect
                results[k] = result
        return results
    return Call(sequence, name=name)


def Join(strands, name=None):
    """
    Returns the result of a strand (or nested structure of strands)
    """
    def join():
        if isinstance(strands, Strand):
            if strands.is_done():
                return strands.get_result()
            key, val = yield First([strands], name=f"Join({name})")
            assert key == 0
            return val
        elif isinstance(strands, list):
            vals = yield Sequence([Join(v, name=name) for v in strands])
            return vals
        else:
            assert isinstance(strands, dict), strands
            vals = yield Sequence({k: Join(v, name=name) for k, v in strands.items()})
            return vals

    return Call(join)


def Fork(effects):
    """Do each of the effects in parallel.
    Returns a strand, whose result reflects the same structure as the effects passed in
    """

    def call_fork(effect):
        val = yield effect
        return val

    def fork_effects(effects):
        if isinstance(effects, Effect):
            return CallFork(call_fork, (effects,))
        elif isinstance(effects, list):
            return [fork_effects(v) for v in effects]
        else:
            assert isinstance(effects, dict)
            return {k: fork_effects(v) for k, v in effects.items()}

    return Sequence(fork_effects(effects))


def Race(effects, name=None):
    """Wait for the first of the effects to finish.
    Returns a tuple with the key of the winning item, and its value
    """
    def race():
        if isinstance(effects, list):
            keys = list(range(len(effects)))
            effects_array = effects
        else:
            assert isinstance(effects, dict)
            keys, effects_array = zip(*effects.items())
        strands = []
        for key, effect in zip(keys, effects_array):
            strand = yield Fork(effect)
            if strand.is_done():
                return key, strand.get_result()
            strands.append(strand)
        i, result = yield First(strands, name=f"Race({name})")
        return keys[i], result
    return Call(race)


def Subscribe(message_key, fn, predicate=None, leading_only=False, latest_only=False):
    """
    Upon receiving any message, runs the specified function on the sent value.
    Returns the strand running the subscription.

    By default, runs on every single message (like takeEvery in redux-saga)
    If leading_only is True, then we don't start new calls to fn while old ones are running (like takeLeading)
    If latest_only is True, then we cancel old calls to make way for new calls (like takeLatest)
    """
    assert not (leading_only and latest_only)

    def subscribe():
        task = None
        while True:
            msg = yield Receive(message_key, predicate=predicate)
            if leading_only:
                yield Call(fn, (msg,))
            else:
                if latest_only and task is not None:
                    yield Cancel(task)
                task = yield CallFork(fn, (msg,))

    return CallFork(subscribe)